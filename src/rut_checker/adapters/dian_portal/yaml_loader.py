"""Lectura acotada y estricta de `selectors.yaml` (T-37).

`pyyaml` es del extra opcional `portal`: solo se importa dentro de las funciones (el módulo se
importa sin pyyaml). Si falta, se falla de forma segura con `SelectorsNotValidatedError`. El
cargador es una subclase de `SafeLoader` que además rechaza claves duplicadas, anclas y alias.
"""

import importlib
from collections.abc import Hashable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rut_checker.domain.errors import SelectorsNotValidatedError, SelectorsReason

if TYPE_CHECKING:  # solo para anotaciones; en ejecución yaml se importa de forma perezosa
    import yaml

MAX_SELECTORS_FILE_BYTES = 64 * 1024


class _DuplicateKeyError(Exception):
    """Clave duplicada en un mapeo YAML."""


def _require_yaml() -> None:
    try:
        importlib.import_module("yaml")
    except ImportError:
        raise SelectorsNotValidatedError(SelectorsReason.YAML_UNAVAILABLE) from None


def _strict_loader_class() -> "type[yaml.SafeLoader]":
    """Construye el cargador estricto (requiere pyyaml ya disponible)."""
    import yaml  # perezoso: pyyaml es del extra opcional `portal`

    class _StrictLoader(yaml.SafeLoader):
        def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
            event = self.peek_event()  # type: ignore[no-untyped-call]  # stub sin tipos
            if getattr(event, "anchor", None) is not None:
                raise yaml.YAMLError("anclas y alias no permitidos")
            return super().compose_node(parent, index)

        # `Any` impuesto por la firma del stub de PyYAML (valores arbitrarios del YAML).
        def construct_mapping(
            self, node: yaml.MappingNode, deep: bool = False
        ) -> dict[Hashable, Any]:
            seen: set[Hashable] = set()
            for key_node, _value_node in node.value:
                key = self.construct_object(key_node, deep=True)
                if isinstance(key, Hashable):
                    if key in seen:
                        raise _DuplicateKeyError
                    seen.add(key)
            return super().construct_mapping(node, deep)

    return _StrictLoader


def _read_bounded(path: Path) -> bytes:
    """Lee el archivo con tope de tamaño (lectura acotada, sin confiar en `stat`)."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_SELECTORS_FILE_BYTES + 1)
    except OSError:
        raise SelectorsNotValidatedError(SelectorsReason.UNREADABLE) from None
    if len(raw) > MAX_SELECTORS_FILE_BYTES:
        raise SelectorsNotValidatedError(SelectorsReason.TOO_LARGE)
    return raw


def _parse(raw: bytes) -> object:
    import yaml  # perezoso: pyyaml es del extra opcional `portal`

    loader = _strict_loader_class()
    try:
        # Subclase de SafeLoader: equivale a `safe_load` con comprobaciones adicionales.
        result: object = yaml.load(raw, Loader=loader)  # noqa: S506
    except _DuplicateKeyError:
        raise SelectorsNotValidatedError(SelectorsReason.DUPLICATE_KEY) from None
    except (yaml.YAMLError, ValueError, RecursionError):
        raise SelectorsNotValidatedError(SelectorsReason.INVALID_YAML) from None
    return result


def read_yaml(path: Path) -> object:
    """Lee `path` (tope de 64 KB) y lo parsea con un `SafeLoader` estricto.

    Raises:
        SelectorsNotValidatedError: pyyaml ausente, archivo ilegible o grande, YAML inválido,
            claves duplicadas, anclas o alias. Sin rutas ni valores en el mensaje.
    """
    _require_yaml()
    return _parse(_read_bounded(path))
