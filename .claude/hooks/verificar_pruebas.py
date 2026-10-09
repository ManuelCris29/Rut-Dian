"""Stop: si hubo cambios en src/ o tests/ desde la última ejecución en verde, corre la suite offline.

Si falla, sale con código 2 para que Claude corrija antes de terminar.
Evita bucles: si Claude ya continuó por este hook (stop_hook_active), no vuelve a bloquear.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import block, project_dir, read_event  # noqa: E402


def latest_mtime(root: Path) -> float:
    paths = [p for d in ("src", "tests") for p in (root / d).rglob("*.py")] if root.exists() else []
    return max((p.stat().st_mtime for p in paths), default=0.0)


def main() -> None:
    event = read_event()
    if event.get("stop_hook_active"):
        sys.exit(0)

    root = project_dir()
    if not (root / "pyproject.toml").exists() or shutil.which("uv") is None:
        sys.exit(0)

    marker = root / ".claude" / "state" / "last_green_tests"
    last_green = marker.stat().st_mtime if marker.exists() else 0.0
    if latest_mtime(root) <= last_green:
        sys.exit(0)

    try:
        result = subprocess.run(
            ["uv", "run", "--quiet", "pytest", "-q", "-x", "-m", "not portal_real"],
            cwd=root, capture_output=True, text=True, timeout=300, check=False,
        )
    except subprocess.TimeoutExpired:
        block("La suite de pruebas superó 5 minutos. Revisa pruebas lentas o con red antes de terminar.")
        return

    # Código 5 = no se recolectaron pruebas (proyecto recién creado): no bloquear.
    if result.returncode in (0, 5):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        sys.exit(0)

    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-30:])
    block(
        "Hay cambios en src/ o tests/ y la suite offline falla. Corrige antes de terminar, "
        "o marca la tarea como BLOQUEADA en specs/tareas.md explicando el motivo.\n" + tail
    )


if __name__ == "__main__":
    main()
