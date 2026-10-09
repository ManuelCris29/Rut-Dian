"""Utilidades compartidas por los hooks del proyecto.

Los hooks reciben un JSON por stdin. Salir con código 2 bloquea la acción (PreToolUse)
o devuelve el mensaje de stderr a Claude para que lo corrija (PostToolUse / Stop).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def read_event() -> dict[str, Any]:
    """Lee el evento JSON de stdin; si no es válido devuelve un dict vacío."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def project_dir() -> Path:
    """Raíz del proyecto según Claude Code (o el directorio actual)."""
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def relative_path(file_path: str) -> str:
    """Ruta relativa a la raíz del proyecto con separadores '/'."""
    if not file_path:
        return ""
    try:
        rel = Path(file_path).resolve().relative_to(project_dir())
    except ValueError:
        rel = Path(file_path)
    return rel.as_posix()


def written_content(tool_input: dict[str, Any]) -> str:
    """Texto que la herramienta va a escribir (Write, Edit o MultiEdit)."""
    parts: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            parts.append(value)
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return "\n".join(parts)


def block(message: str) -> None:
    """Bloquea la acción y explica el motivo a Claude."""
    print(message, file=sys.stderr)
    sys.exit(2)
