"""Funciones puras de enmascarado de identificaciones (Ley 1581 de 2012).

El filtro de logging que las aplica vive en `infra/logging.py` (T-43).
"""

import re

_VISIBLE_DIGITS = 4
_MASK_CHAR = "*"
_MIN_VISIBLE_LENGTH = 7
# Dígitos con separadores comunes (punto, coma, barra, espacio, guion), sin saltos de línea.
_DIGIT_RUN = re.compile(r"\d[\d.,/ -]{4,}\d")


def mask_identification(value: str) -> str:
    """Enmascara una identificación dejando visibles los últimos 4 caracteres (si hay 7 o más).

    Primero se normaliza: se descartan los separadores (todo lo que no sea
    alfanumérico) y luego se enmascara. Así el resultado no revela la longitud
    del formato original ni la posición de puntos o guiones.
    Si quedan 6 o menos caracteres, todo se enmascara (no se revelan 4 de 5);
    con 7 o más quedan visibles los últimos 4. Una entrada no vacía que queda
    vacía tras normalizar (solo separadores) devuelve `*`.

    Ejemplos:
        >>> mask_identification("1234567890")
        '******7890'
        >>> mask_identification("1.000.000.001")
        '******0001'
    """
    compact = "".join(ch for ch in value if ch.isalnum())
    if not compact:
        return _MASK_CHAR if value else ""
    if len(compact) < _MIN_VISIBLE_LENGTH:
        return _MASK_CHAR * len(compact)
    hidden = len(compact) - _VISIBLE_DIGITS
    return _MASK_CHAR * hidden + compact[-_VISIBLE_DIGITS:]


def mask_digit_runs(text: str) -> str:
    r"""Enmascara en texto libre toda secuencia que parezca un número de identificación.

    Reemplaza cada coincidencia de `\d[\d.,/ -]{4,}\d` por `mask_identification`.
    Limitación aceptada: el patrón también casa fechas ISO (`2026-10-09`) y otros
    números largos; es un filtro conservador para mensajes libres. Los campos
    estructurados (fechas, duración) no pasan por este filtro. Las cédulas sueltas
    de 3 a 5 dígitos en texto libre no se enmascaran (el patrón exige 6 caracteres
    como mínimo); la defensa principal es enmascarar en origen. No cruza saltos de línea.
    """
    return _DIGIT_RUN.sub(lambda match: mask_identification(match.group(0)), text)
