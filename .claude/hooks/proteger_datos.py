"""PreToolUse (Read | Write | Edit | MultiEdit): protege secretos, datos personales y guardarraíles.

- Impide leer o escribir `.env` real.
- Impide que los agentes modifiquen hooks y settings (solo el humano los cambia).
- Impide escribir en data/, output/ y logs/ (datos reales, fuera del alcance de los agentes).
- Impide literales con apariencia de identificación real en código y pruebas.
- Impide registrar identificaciones sin enmascarar en logs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import block, read_event, relative_path, written_content  # noqa: E402

# Identificaciones ficticias permitidas (ver skill proteccion-datos-co).
FICTITIOUS_ID = re.compile(r"^(1000000\d{3}|9000000\d{2,3}|1234567890|123456789|12345678)$")
QUOTED_ID_LITERAL = re.compile(r"""["'](\d{6,10})["']""")
UNMASKED_LOG = re.compile(
    r"(logger|logging|log|_log)\.(debug|info|warning|error|exception|critical)\((?P<args>[^\n]*)",
    re.IGNORECASE,
)
SENSITIVE_NAMES = re.compile(r"\b(identification|identification_number|id_number|cedula|nit|raw_id|document_number)\b")

PROTECTED_CONFIG = (".claude/hooks/", ".claude/settings.json")
DATA_DIRS = ("data/", "output/", "logs/")


def is_real_env(rel: str) -> bool:
    name = Path(rel).name
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def main() -> None:
    event = read_event()
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    rel = relative_path(str(tool_input.get("file_path", "")))
    if not rel:
        sys.exit(0)

    if is_real_env(rel):
        block("BLOQUEADO: el archivo .env contiene secretos/configuración local y no se lee ni edita. Usa .env.example.")

    if tool == "Read":
        sys.exit(0)

    if rel.startswith(PROTECTED_CONFIG):
        block(
            f"BLOQUEADO: {rel} es un guardarraíl del proyecto y solo lo modifica el humano. "
            "Si crees que debe cambiar, propón el cambio en tu respuesta."
        )

    if rel.startswith(DATA_DIRS):
        block(f"BLOQUEADO: {rel} es una carpeta de datos reales/salidas; los agentes no escriben ahí.")

    if not rel.endswith(".py"):
        sys.exit(0)

    content = written_content(tool_input)

    if rel.startswith(("src/", "tests/")):
        suspicious = sorted({m for m in QUOTED_ID_LITERAL.findall(content) if not FICTITIOUS_ID.match(m)})
        if suspicious:
            masked = ", ".join("*" * (len(s) - 4) + s[-4:] for s in suspicious[:5])
            block(
                f"BLOQUEADO en {rel}: literales con apariencia de identificación real ({masked}). "
                "Usa solo ids ficticios de la lista blanca (1000000001…, 900000001…) — skill proteccion-datos-co."
            )

    if rel.startswith("src/"):
        for match in UNMASKED_LOG.finditer(content):
            args = match.group("args")
            if SENSITIVE_NAMES.search(args) and "mask" not in args:
                block(
                    f"BLOQUEADO en {rel}: se registra una identificación sin enmascarar en un log: "
                    f"`{match.group(0)[:120]}`. Usa mask_identification() (skill proteccion-datos-co)."
                )

    sys.exit(0)


if __name__ == "__main__":
    main()
