"""Retención (ARQUITECTURA §11, RN-06): detección de vencidos y purga (T-40 aviso, T-44 `purgar`).

Reglas:
- Solo los nombres EXACTOS que genera la aplicación llevan un `run_id` de confianza:
  `resultado_<id>.xlsx|_1.xlsx|.json`, `run_<id>.jsonl`, `snapshot_<id>_<n>.html` y los
  temporales `.resultado_<id>[_1].tmp.*`. Un nombre que solo "contiene" un `run_id` (copias,
  `.bak`, notas) se trata como archivo sin `run_id`.
- Antigüedad: del `run_id` (hora de Bogotá); sin `run_id`, con `run_id` imposible o con
  `run_id` futuro (> now + 1 día) se usa la fecha del archivo: la MÁS RECIENTE entre mtime, ctime
  y creación (una copia de un archivo viejo se considera nueva).
- Datos, resultados y logs vencen a `max_age_days` (<= 365); snapshots a 30 días (o menos si
  `max_age_days` es menor). Temporales `.*.tmp.*` a más de 1 día por fecha del archivo, con o sin
  `run_id` (el margen evita borrar el temporal de una exportación en curso).
- Con `source` (depuración por respuesta contraria de la DIAN, INFORME §9) se seleccionan los
  archivos de nombre exacto de ejecuciones cuyo `run_<id>.jsonl` registró `run_started` con esa
  fuente, SIN importar la edad, en cualquier subcarpeta de las carpetas dadas (p. ej. las que crea
  `--salida`) salvo las excluidas (`data/`). Se omiten los archivos modificados en los últimos 10
  minutos (posible ejecución en curso). Los de ejecuciones sin log o sin `run_started` legible NO
  se borran: se devuelven aparte (`unknown_source`) para revisión manual. Solo se leen las
  primeras líneas de cada log, con tamaño acotado; las líneas inválidas se ignoran.
- Nunca se siguen ni se devuelven enlaces simbólicos o junctions. `purge` solo borra archivos
  regulares cuyo directorio padre, ya resuelto, queda dentro de las carpetas permitidas.
  Riesgo residual (TOCTOU): entre esa comprobación y `unlink` el directorio podría sustituirse
  por un enlace; se mitiga con carpetas de uso exclusivo del operador (ACL, T-60).

`find_expired`/`plan_purge` solo listan; `purge` es lo único que borra y devuelve solo
conteos: ningún mensaje ni valor de retorno incluye rutas.
"""

import os
import re
import stat
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal
from zoneinfo import ZoneInfo

from rut_checker.domain.status import SourceKind
from rut_checker.infra.purge_keys import FileKind, Folder
from rut_checker.infra.run_source import read_run_source

_BOGOTA: Final = ZoneInfo("America/Bogota")
_ID: Final = r"([0-9]{8}-[0-9]{6}-[0-9a-f]{4})"
_EXACT_NAMES: Final = (
    (FileKind.RESULT, re.compile(rf"resultado_{_ID}(?:_1)?\.xlsx|resultado_{_ID}\.json", re.ASCII)),
    (FileKind.RUN_LOG, re.compile(rf"run_{_ID}\.jsonl", re.ASCII)),
    (FileKind.SNAPSHOT, re.compile(rf"snapshot_{_ID}_[0-9]+\.html", re.ASCII)),
    (FileKind.TEMP, re.compile(rf"\.resultado_{_ID}(?:_1)?\.tmp\..+", re.ASCII)),
)
SNAPSHOT_MAX_AGE_DAYS: Final = 30
TEMP_MAX_AGE: Final = timedelta(days=1)
FUTURE_TOLERANCE: Final = timedelta(days=1)
SOURCE_QUIET_PERIOD: Final = timedelta(minutes=10)
_PLACEHOLDERS: Final = frozenset({".gitkeep", ".gitignore"})


@dataclass(frozen=True)
class PurgePlan:
    """Resultado de planificar una purga: qué se borra y qué requiere revisión manual."""

    selected: list[Path] = field(default_factory=list)
    unknown_source: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class PurgeResult:
    """Resultado de `purge`: eliminados y fallidos (los ya inexistentes no cuentan como fallo)."""

    deleted: int
    failed: int


# --- nombres y fechas ----------------------------------------------------------------------


def _exact_name(name: str) -> tuple[FileKind, str] | None:
    """Tipo y `run_id` si `name` es EXACTAMENTE un nombre generado por la aplicación."""
    for kind, pattern in _EXACT_NAMES:
        match = pattern.fullmatch(name)
        if match is not None:
            return kind, next(group for group in match.groups() if group is not None)
    return None


def _run_id_of(name: str) -> str | None:
    exact = _exact_name(name)
    return exact[1] if exact else None


def file_kind(path: Path) -> FileKind:
    """Clasifica un archivo por su nombre (solo nombres exactos; el resto es `OTHER`)."""
    exact = _exact_name(path.name)
    if exact is not None:
        return exact[0]
    if path.name.startswith(".") and ".tmp" in path.name:
        return FileKind.TEMP
    return FileKind.OTHER


def _run_id_moment(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=_BOGOTA)
    except ValueError:
        return None


def _latest_time(st: os.stat_result) -> float:
    """Fecha más reciente entre mtime, ctime y creación (si el sistema la expone)."""
    times = [st.st_mtime, st.st_ctime]
    birth = getattr(st, "st_birthtime", None)
    if isinstance(birth, float):
        times.append(birth)
    return max(times)


def _file_date(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(_latest_time(os.lstat(path)), _BOGOTA)
    except OSError:
        return None


def _moment(path: Path, now: datetime) -> datetime | None:
    """Instante de referencia: `run_id` creíble o, si no, la fecha del archivo."""
    run_id = _run_id_of(path.name)
    from_name = _run_id_moment(run_id) if run_id is not None else None
    if from_name is not None and from_name <= now + FUTURE_TOLERANCE:
        return from_name
    return _file_date(path)


def _is_link(path: Path) -> bool:
    """Enlace simbólico o junction de Windows."""
    return path.is_symlink() or os.path.isjunction(path)


def _files_under(directory: Path) -> Iterable[Path]:
    """Archivos regulares bajo `directory` (sin seguir ni devolver enlaces)."""
    for current, dirnames, filenames in os.walk(directory, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not _is_link(Path(current) / d))
        for name in sorted(filenames):
            path = Path(current) / name
            if not _is_link(path) and name not in _PLACEHOLDERS:
                yield path


def _unique_files(dirs: Iterable[Path]) -> list[Path]:
    """Archivos de todas las carpetas, sin repetir los de carpetas anidadas."""
    seen: set[str] = set()
    files: list[Path] = []
    for directory in dirs:
        if not directory.is_dir() or _is_link(directory):
            continue
        for path in _files_under(directory):
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                files.append(path)
    return files


# --- planificación -------------------------------------------------------------------------


def _is_old(path: Path, now: datetime, max_age_days: int) -> bool:
    kind = file_kind(path)
    if kind is FileKind.TEMP:
        modified = _file_date(path)
        return modified is not None and modified < now - TEMP_MAX_AGE
    days = min(max_age_days, SNAPSHOT_MAX_AGE_DAYS) if kind is FileKind.SNAPSHOT else max_age_days
    moment = _moment(path, now)
    return moment is not None and moment < now - timedelta(days=days)


def _plan_by_source(
    files: list[Path], now: datetime, source: SourceKind, excluded: Sequence[Path]
) -> PurgePlan:
    files = [p for p in files if not any(p.is_relative_to(e) for e in excluded)]
    runs = {
        run_id: read_run_source(path)
        for path in files
        if file_kind(path) is FileKind.RUN_LOG and (run_id := _run_id_of(path.name))
    }
    plan = PurgePlan()
    for path in files:
        run_id = _run_id_of(path.name)
        modified = _file_date(path)
        if run_id is None or modified is None or modified > now - SOURCE_QUIET_PERIOD:
            continue
        if file_kind(path) is FileKind.TEMP and modified >= now - TEMP_MAX_AGE:
            continue
        found = runs.get(run_id)
        if found is source:
            plan.selected.append(path)
        elif found is None:
            plan.unknown_source.append(path)
    return plan


def plan_purge(
    dirs: Iterable[Path],
    now: datetime,
    source: SourceKind | None = None,
    *,
    max_age_days: int = 365,
    source_excluded: Iterable[Path] = (),
) -> PurgePlan:
    """Planifica la purga: archivos a borrar y (con `source`) los de fuente desconocida.

    Args:
        dirs: Carpetas a revisar (`data/`, `output/`, `logs/`); las inexistentes o enlaces
            se ignoran.
        now: Instante actual con zona horaria.
        source: Si se da, solo ejecuciones con esa fuente, sin importar la edad.
        max_age_days: Antigüedad máxima (estrictamente mayor => vencido).
        source_excluded: Carpetas que `source` nunca toca (`data/`).
    """
    files = _unique_files(dirs)
    if source is not None:
        return _plan_by_source(files, now, source, list(source_excluded))
    return PurgePlan(selected=[p for p in files if _is_old(p, now, max_age_days)])


def find_expired(
    dirs: Iterable[Path],
    now: datetime,
    source: SourceKind | None = None,
    *,
    max_age_days: int = 365,
) -> list[Path]:
    """Archivos a purgar (ver `plan_purge`), en orden estable y sin repetidos."""
    return plan_purge(dirs, now, source, max_age_days=max_age_days).selected


def count_by_bucket(paths: Iterable[Path], roots: Sequence[tuple[Folder, Path]]) -> dict[str, int]:
    """Cuenta archivos por `<carpeta>.<tipo>` (claves de `COUNT_KEYS`), en orden estable."""
    counts: dict[str, int] = {}
    for path in paths:
        folder = next((f for f, root in roots if path.is_relative_to(root)), None)
        if folder is not None:
            key = f"{folder.value}.{file_kind(path).value}"
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


# --- purga ---------------------------------------------------------------------------------


def _inside(path: str, root: str) -> bool:
    return Path(os.path.normcase(path)).is_relative_to(os.path.normcase(root))


def _delete(path: Path, roots: list[str]) -> Literal["deleted", "missing", "failed"]:
    """Borra un archivo regular dentro de `roots`."""
    try:
        regular = stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "failed"
    if not regular or not any(_inside(os.path.realpath(path.parent), r) for r in roots):
        return "failed"
    try:
        path.unlink()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "failed"
    return "deleted"


def purge(paths: Iterable[Path], *, within: Iterable[Path]) -> PurgeResult:
    """Elimina los archivos dados y cuenta eliminados y fallidos.

    No borra enlaces, directorios ni archivos fuera de `within` (se cuentan como fallidos).
    Un archivo que ya no existe no cuenta como fallo. Nunca describe rutas. Riesgo residual
    TOCTOU: ver el docstring del módulo.

    Args:
        paths: Archivos candidatos (de `find_expired`).
        within: Carpetas permitidas (`data/`, `output/`, `logs/`).
    """
    roots = [os.path.realpath(root) for root in within]
    outcomes = [_delete(path, roots) for path in paths]
    return PurgeResult(outcomes.count("deleted"), outcomes.count("failed"))
