"""PostToolUse (Write | Edit | MultiEdit): formatea y revisa con ruff el archivo Python editado.

Si quedan errores de lint, sale con código 2 para que Claude los vea y los corrija.
No hace nada si aún no existe pyproject.toml o uv no está instalado.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import block, project_dir, read_event  # noqa: E402


def main() -> None:
    event = read_event()
    file_path = str((event.get("tool_input") or {}).get("file_path", ""))
    root = project_dir()
    if not file_path.endswith(".py") or ".claude" in Path(file_path).parts:
        sys.exit(0)
    if not (root / "pyproject.toml").exists() or shutil.which("uv") is None:
        sys.exit(0)

    def ruff(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "run", "--quiet", "ruff", *args, file_path],
            cwd=root, capture_output=True, text=True, timeout=60, check=False,
        )

    try:
        ruff("format")
        result = ruff("check", "--fix")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        sys.exit(0)

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip().splitlines()
        block("ruff encontró problemas en el archivo editado; corrígelos:\n" + "\n".join(output[:25]))
    sys.exit(0)


if __name__ == "__main__":
    main()
