"""SessionStart: inyecta en el contexto la fase actual, tareas abiertas y las reglas críticas.

Lo que este hook imprime por stdout se añade al contexto de la sesión.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import project_dir  # noqa: E402


def main() -> None:
    root = project_dir()
    estado = root / "docs" / "ESTADO.md"
    tareas = root / "specs" / "tareas.md"
    lines: list[str] = ["## Contexto automático del proyecto (hook SessionStart)"]

    if estado.exists():
        text = estado.read_text(encoding="utf-8")
        for label in ("Fase actual", "Estado de la fase", "Última actualización"):
            match = re.search(rf"\*\*{label}:\*\*\s*(.+)", text)
            if match:
                lines.append(f"- {label}: {match.group(1).strip()}")

    if tareas.exists():
        rows = [r for r in tareas.read_text(encoding="utf-8").splitlines() if r.startswith("| T-")]
        open_rows = [r for r in rows if re.search(r"\|\s*(TODO|EN_CURSO|BLOQUEADA)\s*\|\s*$", r)]
        in_progress = [r for r in open_rows if "EN_CURSO" in r or "BLOQUEADA" in r]
        lines.append(f"- Tareas abiertas: {len(open_rows)} de {len(rows)}")
        for row in in_progress[:5]:
            lines.append(f"  - {row.split('|')[1].strip()} {row.split('|')[2].strip()[:80]} ({row.split('|')[-2].strip()})")

    lines += [
        "- Recuerda: eres el ORQUESTADOR; delega en subagentes y no avances de fase sin /cerrar-fase y aprobación humana.",
        "- Nunca evadir captcha/Turnstile; ids siempre enmascarados en logs; pruebas sin portal real.",
        "- Consulta Context7 antes de usar cualquier API de librería.",
        "- Siguiente paso sugerido: /estado o /iniciar",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
