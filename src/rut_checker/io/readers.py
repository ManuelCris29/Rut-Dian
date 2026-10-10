"""Lector de lotes `.xlsx` / `.csv` (ARQUITECTURA §5.2).

Convenciones:
- `row_index` es la posición 0-based de la fila entre las filas de datos (sin encabezado). Las
  filas totalmente vacías se ignoran pero SÍ ocupan posición, de modo que
  `fila_en_el_archivo = row_index + 2` y el orden original se conserva en la salida.
- Los valores ilegibles no se rechazan aquí: pasan crudos a `InputRow` y los valida el dominio.
- `identificacion`: las celdas numéricas de Excel (`int`/`float`) pasan SIN convertir, porque
  pasar `1.001` a texto lo confundiría con "1.001" (miles). Cualquier otra celda sigue el
  contrato de texto de las demás columnas.
- Demás columnas (texto): `datetime`/`date` -> fecha ISO; `float` entero -> texto sin `.0`;
  `float` con decimales -> `str` sin redondear; `int`/`bool` -> `str`; texto recortado; vacío
  -> `None`. Las fórmulas se leen con `data_only=True`: valor cacheado por Excel (vacío si el
  archivo nunca se calculó).
- Texto: los caracteres de control (salvo tabulador) se REEMPLAZAN por U+FFFD, nunca se eliminan
  (`"100\\x00000001"` no debe volverse un id válido), y se trunca a `MAX_CELL_CHARS + 1`
  caracteres para que el dominio lo rechace por longitud sin cargar textos gigantes.
- Excel: la dimensión declarada en la hoja (`<dimension>`) no es de fiar; se descarta con
  `reset_dimensions()` para no perder filas ni columnas. Solo se lee la primera hoja y debe estar
  visible.
- Lectura perezosa y acotada: archivos > `MAX_INPUT_FILE_BYTES` se rechazan sin abrirse; los
  `.xlsx` se revisan antes (suma descomprimida y razón de compresión) contra bombas zip, con los
  tamaños declarados en el directorio del zip; y la lectura se aborta al superar `max_rows` filas
  no vacías o `max_rows * RAW_ROWS_FACTOR` filas crudas (incluye vacías de relleno).
- Los avisos de openpyxl se silencian: pueden incluir el valor de la celda.
- Nunca se registra ni se incluye en excepciones el contenido de las celdas, ni rutas; el error
  se lanza fuera del `except` para no arrastrar el mensaje original como contexto.
"""

import csv
import datetime as dt
import re
import unicodedata
import warnings
import zipfile
import zlib
from collections.abc import Iterable
from pathlib import Path
from typing import IO
from xml.etree.ElementTree import ParseError

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from rut_checker.domain.errors import InvalidFileReason, InvalidInputFile
from rut_checker.domain.models import InputRow

# Un lote de <= 200 filas pesa kilobytes; 10 MB deja holgura.
MAX_INPUT_FILE_BYTES = 10 * 1024 * 1024
# Suma máxima descomprimida de un .xlsx y razón de compresión máxima por miembro.
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
# Tope por miembro crítico (sharedStrings y hojas): openpyxl los parsea completos y un archivo
# de decenas de MB con razón baja tardaba ~1 min y cientos de MB de memoria.
MAX_CRITICAL_MEMBER_BYTES = 5 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
# Los miembros pequeños comprimen bien de forma legítima: la razón solo se evalúa desde este tamaño.
_RATIO_MIN_MEMBER_BYTES = 1024 * 1024
# Filas crudas (con vacías de relleno) que se leen como máximo: max_rows * factor.
RAW_ROWS_FACTOR = 10
# Más de esto en una celda de texto no es una identificación ni una observación válida.
MAX_CELL_CHARS = 1000
_DELIMITER_PROBE_CHARS = 64 * 1024

_XLSX = ".xlsx"
_CSV = ".csv"
_ID_FIELD = "raw_identification"
_COLUMN_TO_FIELD = {
    "identificacion": _ID_FIELD,
    "dv": "raw_dv",
    "fecha_copia_rut": "raw_copy_date",
    "responsable_validacion": "raw_responsible",
    "observacion": "raw_note",
}
# Controles C0 (salvo tabulador), DEL, C1, no-caracteres U+FFFE/U+FFFF y controles bidi.
_CONTROL_CHARS = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f￾￿‪-‮⁦-⁩]")
_REPLACEMENT = "�"

type _Cells = tuple[object, ...]
type _Values = dict[str, str | int | float | None]
type _RawRow = tuple[int, _Values]


def read_batch(path: Path, max_rows: int) -> list[InputRow]:
    """Lee un lote desde un archivo `.xlsx` (primera hoja) o `.csv`.

    Args:
        path: Archivo de entrada.
        max_rows: Máximo de filas de datos no vacías permitido.

    Returns:
        Filas crudas en el orden del archivo.

    Raises:
        InvalidInputFile: Con un `InvalidFileReason` cerrado (formato, tamaño, ilegible,
            codificación, columna `identificacion` ausente, columnas duplicadas, primera hoja
            oculta, demasiadas filas, vacío).
    """
    suffix = path.suffix.lower()
    if suffix not in (_XLSX, _CSV):
        raise InvalidInputFile(InvalidFileReason.UNSUPPORTED_FORMAT)
    reason = _failure_reason(path, suffix, max_rows)
    if isinstance(reason, InvalidFileReason):
        # Fuera del `except`: sin `__context__` con el mensaje original (puede traer la ruta).
        raise InvalidInputFile(reason)
    # Se construye fuera del `try`: un error propio de validación no se reporta como ilegible.
    return [InputRow(row_index=index, **values) for index, values in reason]


def _failure_reason(path: Path, suffix: str, max_rows: int) -> InvalidFileReason | list[_RawRow]:
    """Lee el archivo; devuelve las filas crudas o el motivo cerrado del fallo de librería."""
    try:
        resolved = path.resolve()
        if not resolved.is_file():
            return InvalidFileReason.UNREADABLE
        if resolved.stat().st_size > MAX_INPUT_FILE_BYTES:
            return InvalidFileReason.TOO_LARGE
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if suffix == _XLSX:
                return _read_xlsx(resolved, max_rows)
            return _read_csv(resolved, max_rows)
    except UnicodeError:
        return InvalidFileReason.NOT_UTF8
    except (
        OSError,
        csv.Error,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        zlib.error,
        EOFError,
        KeyError,
        IndexError,
        ValueError,
        NotImplementedError,
        ParseError,
        InvalidFileException,
    ):
        # Detalle de la librería omitido a propósito: puede contener datos del archivo.
        return InvalidFileReason.UNREADABLE


def _check_zip_is_not_a_bomb(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
    if sum(m.file_size for m in members) > MAX_UNCOMPRESSED_BYTES:
        raise InvalidInputFile(InvalidFileReason.TOO_LARGE)
    for member in members:
        too_compressed = (
            member.file_size >= _RATIO_MIN_MEMBER_BYTES
            and member.file_size > MAX_COMPRESSION_RATIO * max(member.compress_size, 1)
        )
        too_big_critical = _is_critical_member(member.filename) and (
            member.file_size > MAX_CRITICAL_MEMBER_BYTES
        )
        if too_compressed or too_big_critical:
            raise InvalidInputFile(InvalidFileReason.TOO_LARGE)


def _is_critical_member(name: str) -> bool:
    """Miembros que openpyxl parsea completos: cadenas compartidas y hojas."""
    return name == "xl/sharedStrings.xml" or (
        name.startswith("xl/worksheets/") and name.endswith(".xml")
    )


def _read_xlsx(path: Path, max_rows: int) -> list[_RawRow]:
    _check_zip_is_not_a_bomb(path)
    with path.open("rb") as handle:
        workbook = openpyxl.load_workbook(handle, read_only=True, data_only=True)
        try:
            sheet = workbook.worksheets[0]
            if not isinstance(sheet, ReadOnlyWorksheet):
                raise InvalidInputFile(InvalidFileReason.UNREADABLE)
            if sheet.sheet_state != "visible":
                raise InvalidInputFile(InvalidFileReason.FIRST_SHEET_HIDDEN)
            # La dimensión declarada puede estar desactualizada y ocultar filas/columnas.
            sheet.reset_dimensions()
            return _collect((tuple(row) for row in sheet.iter_rows(values_only=True)), max_rows)
        finally:
            workbook.close()


def _read_csv(path: Path, max_rows: int) -> list[_RawRow]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        delimiter = _detect_delimiter(handle)
        return _collect((tuple(row) for row in csv.reader(handle, delimiter=delimiter)), max_rows)


def _detect_delimiter(handle: IO[str]) -> str:
    """Elige `;` o `,` según cuál domina en el encabezado y deja el archivo en el inicio."""
    first_line = handle.readline(_DELIMITER_PROBE_CHARS)
    handle.seek(0)
    return ";" if first_line.count(";") > first_line.count(",") else ","


def _normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "_".join(text.replace("-", " ").split())


def _cell_to_text(value: object) -> str | None:
    """Convierte una celda al contrato de texto de `InputRow`; vacío -> `None`."""
    match value:
        case None:
            return None
        case dt.datetime():
            return value.date().isoformat()
        case dt.date():
            return value.isoformat()
        case bool():
            return str(value)
        case float() if value.is_integer():
            return str(int(value))
        case _:
            text = _CONTROL_CHARS.sub(_REPLACEMENT, str(value).strip())
            return text[: MAX_CELL_CHARS + 1] or None


def _identification_cell(value: object) -> str | int | float | None:
    """Celdas numéricas pasan tal cual (el dominio decide); el resto, como texto."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return _cell_to_text(value)


def _column_positions(header: _Cells) -> dict[str, int]:
    positions: dict[str, int] = {}
    for position, cell in enumerate(header):
        field = _COLUMN_TO_FIELD.get(_normalize_header(cell))
        if field is None:
            continue
        if field in positions:
            raise InvalidInputFile(InvalidFileReason.DUPLICATE_COLUMN)
        positions[field] = position
    if _ID_FIELD not in positions:
        raise InvalidInputFile(InvalidFileReason.MISSING_ID_COLUMN)
    return positions


def _row_values(cells: _Cells, positions: dict[str, int]) -> _Values:
    values: _Values = {}
    for field, pos in positions.items():
        cell = cells[pos] if pos < len(cells) else None
        values[field] = _identification_cell(cell) if field == _ID_FIELD else _cell_to_text(cell)
    return values


def _is_blank(cells: Iterable[object]) -> bool:
    return all(_cell_to_text(cell) is None for cell in cells)


def _collect(rows: Iterable[_Cells], max_rows: int) -> list[_RawRow]:
    """Consume las filas de forma perezosa y aborta en cuanto se superan los topes."""
    iterator = iter(rows)
    header = next(iterator, None)
    if header is None:
        raise InvalidInputFile(InvalidFileReason.EMPTY)
    positions = _column_positions(header)
    raw_limit = max_rows * RAW_ROWS_FACTOR
    result: list[_RawRow] = []
    for index, cells in enumerate(iterator):
        if index >= raw_limit:
            raise InvalidInputFile(InvalidFileReason.TOO_MANY_RAW_ROWS)
        if _is_blank(cells):
            continue
        if len(result) >= max_rows:
            raise InvalidInputFile(InvalidFileReason.TOO_MANY_ROWS)
        result.append((index, _row_values(cells, positions)))
    return result
