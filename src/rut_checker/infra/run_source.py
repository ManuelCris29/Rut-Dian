"""Lectura acotada de la fuente de una ejecución (evento `run_started` de su log JSONL)."""

import json
from pathlib import Path
from typing import Final

from rut_checker.domain.status import SourceKind

_HEAD_LINES: Final = 50
_MAX_LINE_CHARS: Final = 65_536


def _event_of(line: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _as_source(value: object) -> SourceKind | None:
    try:
        return SourceKind(value) if isinstance(value, str) else None
    except ValueError:
        return None


def read_run_source(log_path: Path) -> SourceKind | None:
    """Fuente del evento `run_started` de un log de ejecución; `None` si no se puede saber.

    Lee a lo sumo las primeras líneas, de tamaño acotado, y descarta las inválidas.
    """
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(_HEAD_LINES):
                line = handle.readline(_MAX_LINE_CHARS)
                if not line:
                    return None
                event = _event_of(line)
                if event is not None and event.get("event") == "run_started":
                    return _as_source(event.get("source"))
    except OSError:
        return None
    return None
