"""Claves cerradas de la purga (T-44): carpetas, tipos de archivo y conteos permitidos en el log.

Módulo hoja compartido por `retention.py` (que cuenta) y `log_format.py` (que valida la lista
blanca de `purge_counts`): ningún texto libre puede llegar al log.
"""

from enum import StrEnum
from typing import Final


class Folder(StrEnum):
    """Carpetas de trabajo cubiertas por la purga."""

    DATA = "data"
    OUTPUT = "output"
    LOGS = "logs"


class FileKind(StrEnum):
    """Tipo de archivo por su nombre (los nombres solo llevan `run_id`, nunca datos)."""

    RESULT = "resultado"
    RUN_LOG = "log"
    SNAPSHOT = "snapshot"
    TEMP = "temporal"
    OTHER = "otro"


TOTAL_DELETED: Final = "deleted"
TOTAL_FAILED: Final = "failed"
# Archivos de ejecuciones sin log de fuente legible (`--fuente`): no se borran, se revisan a mano.
UNKNOWN_SOURCE: Final = "unknown_source"
COUNT_KEYS: Final = frozenset(
    {f"{folder.value}.{kind.value}" for folder in Folder for kind in FileKind}
    | {TOTAL_DELETED, TOTAL_FAILED, UNKNOWN_SOURCE}
)
