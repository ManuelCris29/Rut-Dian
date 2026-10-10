"""Rutas seguras para salidas, logs y datos (T-40b, ARQUITECTURA §6 y §11, Obs-4).

Reglas:
- `--salida` debe quedar, tras `resolve()` (symlinks/junctions), dentro de `RUT_OUTPUT_DIR`.
- Las carpetas de trabajo no pueden estar dentro de un árbol git, salvo `<raíz>/output`,
  `<raíz>/logs` y `<raíz>/data` exactas (y su contenido) **si el `.gitignore` de esa raíz las
  lista**. Un repositorio ajeno sin ese `.gitignore` se rechaza.
- El árbol git se detecta buscando `.git` (directorio o archivo) en la ruta o sus padres,
  sin invocar git.
- Se rechazan componentes peligrosos en Windows (flujos `:`, nombres reservados, punto o
  espacio final); la regla se aplica en todas las plataformas para que sea determinista.
- Las carpetas sincronizadas (OneDrive, Dropbox, Google Drive, iCloud, Box, Nextcloud) solo
  generan aviso.

Ningún mensaje de error incluye la ruta ni encadena la excepción original: los motivos son un
conjunto cerrado.
"""

import os
from pathlib import Path

from rut_checker.domain.errors import UnsafePathError, UnsafePathReason
from rut_checker.infra.settings import Settings

# Debe coincidir con los valores por defecto de `Settings` (lo verifica una prueba).
IGNORED_DEFAULT_DIRS = ("output", "logs", "data")
_SYNCED_PREFIXES = (
    "onedrive",
    "dropbox",
    "googledrive",
    "google drive",
    "iclouddrive",
    "nextcloud",
)
_SYNCED_NAMES = frozenset({"my drive", "mi unidad", "box", "box sync", "icloud drive"})
_SYNCED_ENV_VARS = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


def _has_unsafe_component(path: Path) -> bool:
    """Indica si algún componente (fuera de la unidad) es peligroso en Windows."""
    parts = path.parts[1:] if path.anchor else path.parts
    for part in parts:
        if part in (".", ".."):
            continue
        if ":" in part or part.endswith((".", " ")):
            return True
        if part.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES:
            return True
    return False


def _resolve(path: Path) -> Path:
    """Resuelve la ruta (siguiendo enlaces); lo imposible de resolver es inválido.

    La excepción se lanza fuera del `except` para no encadenar el error original (su texto
    podría contener la ruta).
    """
    resolved: Path | None = None
    if not _has_unsafe_component(path):
        try:
            resolved = path.resolve()
        except (OSError, ValueError, RuntimeError):
            resolved = None
    if resolved is None:
        raise UnsafePathError(UnsafePathReason.INVALID_PATH)
    return resolved


def _same(left: Path, right: Path) -> bool:
    return os.path.normcase(left) == os.path.normcase(right)


def _is_within(path: Path, base: Path) -> bool:
    """Indica si `path` es `base` o está dentro de ella (comparación insensible en Windows)."""
    return Path(os.path.normcase(path)).is_relative_to(os.path.normcase(base))


def _find_git_root(resolved: Path) -> Path | None:
    """Primer ancestro (o la propia ruta) que contiene `.git` como directorio o archivo."""
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _gitignore_lists(root: Path, name: str) -> bool:
    """Indica si el `.gitignore` de `root` lista `name` con una línea exacta.

    Acepta `name`, `name/`, `/name` y `/name/`. Ante la duda se devuelve False: archivo
    ilegible o línea de negación (`!`) que afecte a la carpeta.
    """
    try:
        content = (root / ".gitignore").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    accepted = {name, f"{name}/", f"/{name}", f"/{name}/"}
    listed = False
    for raw in content.splitlines():
        line = raw.strip()
        if line in accepted:
            listed = True
        elif line.startswith("!") and line[1:].strip("/").split("/")[0] == name:
            return False
    return listed


def assert_safe_dir(path: Path) -> None:
    """Rechaza `path` si, resuelto, queda dentro de un árbol git fuera de las carpetas ignoradas.

    Raises:
        UnsafePathError: motivo `INSIDE_GIT_TREE` o `INVALID_PATH`.
    """
    resolved = _resolve(path)
    root = _find_git_root(resolved)
    if root is None:
        return
    for name in IGNORED_DEFAULT_DIRS:
        # La excepción vale solo si la carpeta por defecto resuelve a sí misma (no es un enlace
        # hacia otra parte del repositorio) y el .gitignore de la raíz la lista.
        allowed = _resolve(root / name)
        if (
            _same(allowed, root / name)
            and _is_within(resolved, allowed)
            and _gitignore_lists(root, name)
        ):
            return
    raise UnsafePathError(UnsafePathReason.INSIDE_GIT_TREE)


def resolve_output_path(requested: Path | None, settings: Settings) -> Path:
    """Devuelve la carpeta de salida efectiva, validada.

    Sin `requested` se usa `RUT_OUTPUT_DIR`. Una ruta relativa se interpreta respecto a
    `RUT_OUTPUT_DIR` (no al directorio actual); en ambos casos, tras `resolve()` debe quedar
    dentro de ella, lo que bloquea `..` y los enlaces que escapen.

    Raises:
        UnsafePathError: la carpeta base o el destino están en un árbol git no permitido,
            la ruta es inválida o queda fuera de la carpeta de salida.
    """
    base = _resolve(settings.output_dir)
    assert_safe_dir(base)
    if requested is None:
        return base
    if chr(0) in str(requested):
        raise UnsafePathError(UnsafePathReason.INVALID_PATH)
    resolved = _resolve(requested if requested.is_absolute() else base / requested)
    if not _is_within(resolved, base):
        raise UnsafePathError(UnsafePathReason.OUTSIDE_OUTPUT_DIR)
    assert_safe_dir(resolved)  # detecta un .git anidado dentro de la carpeta de salida
    return resolved


def _env_synced_roots() -> list[Path]:
    roots: list[Path] = []
    for var in _SYNCED_ENV_VARS:
        value = os.environ.get(var)
        if value:
            try:
                roots.append(_resolve(Path(value)))
            except UnsafePathError:
                continue
    return roots


def is_synced_folder(path: Path) -> bool:
    """Indica si la ruta parece estar en una carpeta sincronizada en la nube.

    Es solo un aviso para la CLI (Obs-4): nunca lanza y no bloquea la ejecución.
    """
    try:
        resolved = _resolve(path)
    except UnsafePathError:
        return False
    for part in resolved.parts:
        name = part.lower()
        if name.startswith(_SYNCED_PREFIXES) or name in _SYNCED_NAMES:
            return True
    return any(_is_within(resolved, root) for root in _env_synced_roots())


def ensure_private_dir(path: Path) -> None:
    """Crea `path` si no existe, validándola antes y después de crearla (TOCTOU).

    Se crea sobre la ruta resuelta. En POSIX la carpeta final queda con modo 0o700; en Windows
    no se tocan las ACL: las configura el administrador en la instalación (T-60).

    Raises:
        UnsafePathError: la carpeta no es segura, no se pudo crear o cambió al crearse (en ese
            caso no se debe escribir en ella).
    """
    resolved = _resolve(path)
    assert_safe_dir(resolved)
    if resolved.is_dir():
        return
    failed = False
    try:
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            resolved.chmod(0o700)  # mkdir está sujeto a umask y no afecta a padres ya creados
    except OSError:
        failed = True
    if failed:
        raise UnsafePathError(UnsafePathReason.INVALID_PATH)
    assert_safe_dir(resolved)
    if not _same(_resolve(resolved), resolved):
        raise UnsafePathError(UnsafePathReason.INVALID_PATH)
