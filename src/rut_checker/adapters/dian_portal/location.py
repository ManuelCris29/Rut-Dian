"""Ubicación segura de `selectors.yaml` y de su snapshot (B-1, T-37).

La raíz del proyecto se ancla al paquete (`pyproject.toml` con `name = "rut-checker"`), nunca al
archivo pedido. Si el paquete corre fuera de un árbol de proyecto (p. ej. instalado en
`site-packages`), el portal no se puede habilitar (`OUTSIDE_PROJECT`).
"""

import os
import tomllib
from pathlib import Path, PurePosixPath

from rut_checker.domain.errors import SelectorsNotValidatedError, SelectorsReason

_PROJECT_NAME = "rut-checker"
_SNAPSHOT_DIR = PurePosixPath("docs/investigacion")


def _outside() -> SelectorsNotValidatedError:
    return SelectorsNotValidatedError(SelectorsReason.OUTSIDE_PROJECT)


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _is_project_pyproject(candidate: Path) -> bool:
    try:
        data = tomllib.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # TOMLDecodeError y UnicodeDecodeError son ValueError
        return False
    project = data.get("project")
    return isinstance(project, dict) and project.get("name") == _PROJECT_NAME


def _find_project_root(start: Path) -> Path | None:
    """Sube desde `start` hasta el `pyproject.toml` de `rut-checker`; `None` si no hay."""
    for parent in start.resolve().parents:
        candidate = parent / "pyproject.toml"
        if candidate.is_file() and _is_project_pyproject(candidate):
            return parent
    return None


def _project_root() -> Path:
    root = _find_project_root(Path(__file__))
    if root is None:
        raise _outside()
    return root


def project_root() -> Path:
    """Raíz del proyecto (ancla al paquete); `OUTSIDE_PROJECT` si no hay árbol de proyecto."""
    return _project_root()


def _check_location(path: Path, root: Path) -> None:
    """Solo `<raíz>/config/selectors.yaml`, sin enlaces simbólicos ni junctions."""
    expected = root / "config" / "selectors.yaml"
    given = Path(os.path.abspath(path))
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        raise _outside() from None
    if resolved != expected or _is_link(given) or _is_link(given.parent):
        raise _outside()
    if not expected.is_file():
        raise SelectorsNotValidatedError(SelectorsReason.UNREADABLE)


def _snapshot_exists(source_snapshot: str, root: Path) -> bool:
    """El snapshot debe ser una ruta relativa dentro de `docs/investigacion/` y existir."""
    posix = PurePosixPath(source_snapshot)
    if (
        not source_snapshot
        or "\\" in source_snapshot
        or posix.is_absolute()
        or ".." in posix.parts
        or _SNAPSHOT_DIR not in posix.parents
    ):
        return False
    base = (root / _SNAPSHOT_DIR).resolve()
    candidate = (root / Path(*posix.parts)).resolve()
    return candidate.is_relative_to(base) and candidate.is_file()
