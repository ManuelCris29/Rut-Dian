r"""Exportadores planos CSV y JSON (T-47, ARQUITECTURA §5.3).

Reutilizan `exporters.build_row` (mismas 8 columnas de SPEC §5, fecha en Bogotá y nota del
área ausente en filas inválidas) y `write_atomic` (temporal + `os.replace`, sin sobrescribir).

- CSV: UTF-8 con BOM (Excel en Windows), `csv` de stdlib con quoting mínimo y neutralización por
  el primer carácter visible: tras saltar espacios y caracteres invisibles (categoría Cf) se
  prefija un apóstrofo visible si empieza por `= + - @ |`, tab, CR o su equivalente de ancho
  completo (NFKC). Un tab o CR inicial se neutraliza siempre.
- JSON: lista de objetos con las 8 claves, UTF-8 sin escapar no ASCII; no neutraliza fórmulas
  (no es una hoja de cálculo) y json escapa los caracteres de control. Los caracteres que UTF-8
  no admite (surrogates sueltos) se reemplazan por U+FFFD, como en el Excel.
- Fallo al escribir: reintento con `<nombre>_1.<ext>`; el CSV cae además a JSON de respaldo
  (`JSON_BACKUP`, código 3 en la CLI). Si todo falla, `ExportError` genérico sin valores.
- Este módulo no registra en logs.
"""

import csv
import unicodedata
from pathlib import Path
from typing import Final

from rut_checker.domain.errors import ExportError, UnsafePathError, UnsafePathReason
from rut_checker.domain.models import QueryOutcome
from rut_checker.io.exporters import (
    COLUMNS,
    ExportKind,
    ExportReport,
    Row,
    Writer,
    build_row,
    sanitize_cell,
    write_atomic,
    write_json_rows,
)

_QUOTE: Final = "'"
_ALWAYS_DANGEROUS: Final = frozenset("\t\r")
_DANGEROUS_AFTER_NFKC: Final = frozenset("=+-@|")


# Ignorables por defecto de Unicode que no son Cf (Mn/Lo): Excel puede ignorarlos al interpretar.
_IGNORABLE_CODES: Final = frozenset({0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0})
_IGNORABLE_RANGES: Final = ((0x180B, 0x180D), (0xFE00, 0xFE0F))


def _is_invisible(char: str) -> bool:
    code = ord(char)
    return (
        char.isspace()
        or unicodedata.category(char) == "Cf"
        or code in _IGNORABLE_CODES
        or any(low <= code <= high for low, high in _IGNORABLE_RANGES)
    )


def _is_dangerous(char: str) -> bool:
    return char in _ALWAYS_DANGEROUS or unicodedata.normalize("NFKC", char)[:1] in (
        _DANGEROUS_AFTER_NFKC
    )


def neutralize_visible(value: str) -> str:
    """Prefija con apóstrofo si el primer carácter visible puede interpretarse como fórmula."""
    for char in value:
        if char in _ALWAYS_DANGEROUS:
            return _QUOTE + value
        if _is_invisible(char):
            continue
        return _QUOTE + value if _is_dangerous(char) else value
    return value


def _csv_cell(value: str) -> str:
    """Saltos de línea -> espacio (ninguna línea física empieza por fórmula) y neutralización."""
    flat = sanitize_cell(value).replace("\r", " ").replace("\n", " ")
    return neutralize_visible(flat)


def _write_csv(rows: list[Row], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def _check_target(path: Path, output_dir: Path, suffix: str) -> None:
    if path.resolve().parent != output_dir.resolve():
        raise UnsafePathError(UnsafePathReason.OUTSIDE_OUTPUT_DIR)
    if path.suffix.lower() != suffix:
        raise UnsafePathError(UnsafePathReason.INVALID_PATH)


def _write_with_fallback(
    rows: list[Row],
    path: Path,
    writer: Writer,
    kinds: tuple[ExportKind, ExportKind],
    *,
    json_backup_dir: Path | None,
) -> ExportReport:
    """Destino, alternativo `_1` y, si se pide, JSON de respaldo; si no, `ExportError`."""
    alternative = path.with_name(f"{path.stem}_1{path.suffix}")
    for target, kind in ((path, kinds[0]), (alternative, kinds[1])):
        if write_atomic(target, writer, rows):
            return ExportReport(target, kind)
    if json_backup_dir is not None:
        backup = json_backup_dir / f"{path.stem}.json"
        if write_atomic(backup, write_json_rows, rows):
            return ExportReport(backup, ExportKind.JSON_BACKUP)
    raise ExportError from None


def export_csv(outcomes: list[QueryOutcome], path: Path, *, output_dir: Path) -> ExportReport:
    """Escribe el CSV (UTF-8 con BOM) con las columnas de SPEC §5, celdas neutralizadas.

    Args:
        outcomes: Desenlaces en el orden original de la entrada.
        path: Destino `output_dir/resultado_<run_id>.csv` directamente dentro de `output_dir`.
        output_dir: Directorio de salida (el de `RUT_OUTPUT_DIR`).

    Returns:
        `ExportReport` con `CSV`, `CSV_ALTERNATIVE` o `JSON_BACKUP` (código 3 en la CLI).

    Raises:
        UnsafePathError: Ruta fuera de `output_dir` o sufijo distinto de `.csv`.
        ExportError: Fallaron los tres destinos (mensaje genérico).
    """
    _check_target(path, output_dir, ".csv")
    rows = [build_row(outcome, _csv_cell) for outcome in outcomes]
    kinds = (ExportKind.CSV, ExportKind.CSV_ALTERNATIVE)
    # El respaldo JSON usa las mismas celdas ya neutralizadas del CSV.
    return _write_with_fallback(rows, path, _write_csv, kinds, json_backup_dir=output_dir)


def export_json(outcomes: list[QueryOutcome], path: Path, *, output_dir: Path) -> ExportReport:
    """Escribe el JSON (lista de objetos con las 8 claves de SPEC §5), sin neutralizar.

    Args:
        outcomes: Desenlaces en el orden original de la entrada.
        path: Destino `output_dir/resultado_<run_id>.json` directamente dentro de `output_dir`.
        output_dir: Directorio de salida (el de `RUT_OUTPUT_DIR`).

    Returns:
        `ExportReport` con `JSON` o `JSON_ALTERNATIVE`.

    Raises:
        UnsafePathError: Ruta fuera de `output_dir` o sufijo distinto de `.json`.
        ExportError: Fallaron ambos destinos (mensaje genérico).
    """
    _check_target(path, output_dir, ".json")
    rows = [build_row(outcome, sanitize_cell) for outcome in outcomes]
    kinds = (ExportKind.JSON, ExportKind.JSON_ALTERNATIVE)
    return _write_with_fallback(rows, path, write_json_rows, kinds, json_backup_dir=None)
