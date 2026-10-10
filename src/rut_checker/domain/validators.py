"""Normalización y validación de formato de identificaciones (T-41).

Reglas (ARQUITECTURA §5.2, skill `validacion-identificacion`):
- La entrada es solo el número; no hay columna de tipo CC/NIT (P-4). Un número de 9-10 dígitos
  puede ser cédula o NIT, así que el DV se trata por presencia: si llega (columna o sufijo `-d`)
  se valida con `stdnum.co.nit.calc_check_digit`; si no llega, no se calcula ni se exige.
- Longitud [SUPUESTO]: 3 a 10 dígitos (cédula 3-10; NIT 9-10 sin DV; la unión es 3-10).
- Los ceros iniciales se conservan y se aceptan (pendiente de confirmar con negocio); el valor
  cero (`0`, `000`) se rechaza por fuera de rango.
- Los motivos de rechazo son `InvalidReason` (conjunto cerrado): nunca incluyen el valor crudo.
"""

import math
import re

from stdnum.co import nit

from rut_checker.domain.errors import InvalidIdentification, InvalidReason
from rut_checker.domain.models import IdentificationInput

MIN_LENGTH = 3
MAX_LENGTH = 10
# Un float (doble precisión) representa enteros exactos solo hasta 2**53; por encima se pierden
# dígitos y es preferible rechazar a adivinar. Las identificaciones válidas (<= 10 dígitos) caben.
_MAX_EXACT_FLOAT = 2**53

_DIGITS = re.compile(r"[0-9]+")
_SINGLE_DIGIT = re.compile(r"[0-9](?:\.0+)?")
_DECIMAL_ZEROS = re.compile(r"([0-9]+)[.,]0{1,2}")
_SPACE_BETWEEN_DIGITS = re.compile(r"[0-9]\s+[0-9]")
_GROUPED = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]{1,3}(?:,[0-9]{3})+")
# Guiones Unicode (U+2010 a U+2015) y signo menos (U+2212) que Excel/Word suelen producir.
_UNICODE_DASHES = str.maketrans(dict.fromkeys([*range(0x2010, 0x2016), 0x2212], "-"))


def normalize_identification(raw: object) -> tuple[str, str | None]:
    """Normaliza el valor crudo de una identificación.

    Acepta texto, enteros y flotantes de Excel sin parte decimal (`1000000001.0` → `"1000000001"`).
    En texto:
    - Todo espacio en blanco (incluido el no separable) se elimina, también como separador de
      grupos (`"1 000 000 001"`); pero si el texto contiene `.` o `,`, un espacio entre dígitos
      se rechaza (`"900.000 000"`, `"1 000,000"`): mezclar tipos de separador es ambiguo.
    - Los guiones Unicode se tratan como `-`; un único `-` separa el DV final.
    - `.` y `,` solo se aceptan como (a) parte decimal nula de 1 o 2 ceros (`"900000001.0"`,
      `"12345678,00"`) o (b) separador de miles con agrupamiento válido de un solo tipo
      (`"900.000.001"`, `"1,000,000,001"`; tres ceros tras el separador son miles: `"1.000"`
      es 1000). Cualquier otro uso (`"12.34"`, `"1,2,3"`, `"1.000,000"`) se rechaza como no
      numérico: nunca se adivina.
    Los flotantes con decimales, no finitos, mayores que 2**53 (pierden precisión) o en
    notación científica como texto (`"1E9"`) se rechazan. No valida la longitud del texto ni el
    DV; solo un entero `>= 10**10` se rechaza ya por longitud.

    Args:
        raw: Valor crudo de la celda o campo.

    Returns:
        Tupla `(número_solo_dígitos, dv_del_sufijo_o_None)`.

    Raises:
        InvalidIdentification: Vacío, no numérico o DV de sufijo mal formado.
    """
    if raw is None:
        raise InvalidIdentification(InvalidReason.EMPTY)
    if isinstance(raw, bool):
        raise InvalidIdentification(InvalidReason.NON_NUMERIC)
    if isinstance(raw, int):
        return _numeric_to_digits(raw), None
    if isinstance(raw, float):
        return _float_to_digits(raw), None
    if isinstance(raw, str):
        return _split_text(raw)
    raise InvalidIdentification(InvalidReason.NON_NUMERIC)


def _numeric_to_digits(value: int) -> str:
    if value < 0:
        raise InvalidIdentification(InvalidReason.NON_NUMERIC)
    if value >= 10**MAX_LENGTH:
        raise InvalidIdentification(InvalidReason.LENGTH_OUT_OF_RANGE)
    return str(value)


def _float_to_digits(value: float) -> str:
    if not math.isfinite(value) or not value.is_integer() or abs(value) > _MAX_EXACT_FLOAT:
        raise InvalidIdentification(InvalidReason.NON_NUMERIC)
    return _numeric_to_digits(int(value))


def _strip_separators(base: str) -> str:
    """Quita `.`/`,` solo si son decimales nulos o miles bien agrupados; si no, rechaza."""
    if _DIGITS.fullmatch(base):
        return base
    decimal = _DECIMAL_ZEROS.fullmatch(base)
    grouped = _GROUPED.fullmatch(base)
    if decimal and not grouped:
        return decimal.group(1)
    if grouped and not decimal:
        return base.replace(".", "").replace(",", "")
    raise InvalidIdentification(InvalidReason.NON_NUMERIC)


def _split_text(text: str) -> tuple[str, str | None]:
    translated = text.translate(_UNICODE_DASHES)
    if ("." in translated or "," in translated) and _SPACE_BETWEEN_DIGITS.search(translated):
        raise InvalidIdentification(InvalidReason.NON_NUMERIC)
    compact = "".join(translated.split())
    if not compact:
        raise InvalidIdentification(InvalidReason.EMPTY)
    base, separator, suffix = compact.partition("-")
    base = _strip_separators(base)
    if not separator:
        return base, None
    if not suffix or "-" in suffix:
        raise InvalidIdentification(InvalidReason.NON_NUMERIC)
    if _DIGITS.fullmatch(suffix) is None or len(suffix) != 1:
        raise InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)
    return base, suffix


def _normalize_dv_column(dv: str | None) -> str | None:
    """Normaliza el DV de la columna; vacío significa que no llegó."""
    if dv is None or not dv.strip():
        return None
    candidate = dv.strip()
    if _SINGLE_DIGIT.fullmatch(candidate) is None:
        raise InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)
    return candidate[0]


def validate_identification(raw: object, dv: str | None) -> IdentificationInput:
    """Normaliza y valida formato, longitud y DV de una identificación.

    Si el DV llega por sufijo y por columna, ambos deben coincidir. Sin DV no se calcula nada.
    La posición de la fila no interviene: `BatchQueryService` la conoce por `InputRow.row_index`.

    Args:
        raw: Valor crudo de la identificación (texto, int o float de Excel).
        dv: Valor crudo de la columna `dv`, si existe (`"7"` o `"7.0"` de Excel).

    Returns:
        La entrada validada.

    Raises:
        InvalidIdentification: Con un `InvalidReason` cerrado (sin el valor crudo).
    """
    number, suffix_dv = normalize_identification(raw)
    if not MIN_LENGTH <= len(number) <= MAX_LENGTH or int(number) == 0:
        raise InvalidIdentification(InvalidReason.LENGTH_OUT_OF_RANGE)
    column_dv = _normalize_dv_column(dv)
    if suffix_dv is not None and column_dv is not None and suffix_dv != column_dv:
        raise InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)
    final_dv = suffix_dv if suffix_dv is not None else column_dv
    if final_dv is not None and nit.calc_check_digit(number) != final_dv:
        raise InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)
    return IdentificationInput(identification=number, dv=final_dv)
