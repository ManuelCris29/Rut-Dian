"""Retención (ARQUITECTURA §11, RN-06): detección de archivos vencidos.

Versión mínima de T-40 para el aviso de la CLI; T-44 (`purgar`) la reutiliza y la extiende
(snapshots a 30 días, filtro por fuente, temporales). Solo lista: nunca borra.

La antigüedad sale del `run_id` del nombre (`AAAAMMDD-HHMMSS-<4 hex>`, hora de Bogotá); si el
nombre no lo trae o la fecha es imposible se usa la fecha de modificación (mtime).
"""

import os
import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

_BOGOTA: Final = ZoneInfo("America/Bogota")
_RUN_ID: Final = re.compile(r"(?<![0-9])([0-9]{8}-[0-9]{6})-[0-9a-f]{4}(?![0-9a-f])", re.ASCII)


def _run_id_moment(name: str) -> datetime | None:
    match = _RUN_ID.search(name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=_BOGOTA)
    except ValueError:
        return None


def _moment(path: Path) -> datetime | None:
    """Instante de referencia del archivo; `None` si no se puede leer."""
    from_name = _run_id_moment(path.name)
    if from_name is not None:
        return from_name
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, _BOGOTA)
    except OSError:
        return None


def _files_under(directory: Path) -> Iterable[Path]:
    """Archivos regulares bajo `directory` (sin seguir enlaces simbólicos)."""
    for current, dirnames, filenames in os.walk(directory, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(current) / name
            if not path.is_symlink():
                yield path


def find_expired(dirs: Iterable[Path], now: datetime, max_age_days: int = 365) -> list[Path]:
    """Archivos con más de `max_age_days` días de antigüedad, en orden estable.

    Args:
        dirs: Carpetas a revisar (`data/`, `output/`, `logs/`); las que no existen se ignoran.
        now: Instante actual con zona horaria.
        max_age_days: Antigüedad máxima (estrictamente mayor => vencido).
    """
    limit = now - timedelta(days=max_age_days)
    expired: list[Path] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in _files_under(directory):
            moment = _moment(path)
            if moment is not None and moment < limit:
                expired.append(path)
    return expired
