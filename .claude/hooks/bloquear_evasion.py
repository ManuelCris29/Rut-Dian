"""PreToolUse (Bash | Write | Edit | MultiEdit): bloquea técnicas de evasión de controles.

Regla del proyecto (CLAUDE.md §3): no se evaden CAPTCHA, Cloudflare Turnstile ni mecanismos
antibot, y no se consulta la DIAN por HTTP directo.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import block, read_event, relative_path, written_content  # noqa: E402

FORBIDDEN_PACKAGES = (
    r"playwright[-_]stealth|undetected[-_]chromedriver|selenium[-_]stealth|selenium[-_]wire|"
    r"puppeteer-extra|2captcha|twocaptcha|anti-?captcha|capsolver|capmonster|deathbycaptcha|"
    r"nopecha|cloudscraper|curl[-_]cffi|camoufox|nodriver|botasaurus|playwright-extra"
)

INSTALL_CMD = re.compile(
    r"(pip3?\s+install|uv\s+add|uv\s+pip\s+install|poetry\s+add|npm\s+(i|install|add)|"
    r"pnpm\s+add|yarn\s+add|npx)\b[^\n]*\b(" + FORBIDDEN_PACKAGES + r")\b",
    re.IGNORECASE,
)

DIRECT_HTTP_TO_DIAN = re.compile(
    r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|httpie|http)\b[^\n]*dian\.gov\.co",
    re.IGNORECASE,
)

FORBIDDEN_CODE = [
    (re.compile(r"^\s*(import|from)\s+(" + FORBIDDEN_PACKAGES.replace("-", "_") + r")", re.I | re.M),
     "importa una librería de evasión antibot/captcha"),
    (re.compile(r"navigator\.webdriver", re.I), "manipula navigator.webdriver para ocultar la automatización"),
    (re.compile(r"AutomationControlled", re.I), "desactiva banderas de automatización del navegador"),
    (re.compile(r"\bstealth_(sync|async)\b|\bStealth\(", re.I), "usa modo stealth"),
    (re.compile(r"\b(solve|bypass|crack)_?(captcha|turnstile|challenge)", re.I),
     "intenta resolver o saltar un desafío de seguridad"),
    (re.compile(r"cf[-_]clearance", re.I), "reutiliza cookies de Cloudflare para saltar el desafío"),
    (re.compile(r"javax\.faces\.ViewState", re.I),
     "reproduce el estado interno JSF por HTTP (endpoint no documentado)"),
]

# Documentación y configuración de Claude pueden mencionar estos términos para prohibirlos.
SKIP_PREFIXES = (".claude/", "docs/", "specs/")
SKIP_FILES = {"CLAUDE.md", "README.md"}
CODE_SUFFIXES = {".py", ".js", ".ts", ".toml", ".txt", ".cfg", ".ini", ".json", ".yaml", ".yml", ".lock"}


def check_bash(command: str) -> None:
    if INSTALL_CMD.search(command):
        block(
            "BLOQUEADO por cumplimiento: intento de instalar una librería de evasión antibot/captcha. "
            "El proyecto prohíbe evadir controles de la DIAN (CLAUDE.md §3). "
            "Ante un desafío de seguridad el sistema debe pausar y ceder al operador."
        )
    if DIRECT_HTTP_TO_DIAN.search(command):
        block(
            "BLOQUEADO: no se consulta la DIAN por HTTP directo desde la terminal. "
            "Para investigar usa WebFetch/WebSearch; para observar el portal, Playwright MCP según el agente investigador-dian."
        )


def check_write(tool_input: dict) -> None:
    rel = relative_path(str(tool_input.get("file_path", "")))
    if rel.startswith(SKIP_PREFIXES) or rel in SKIP_FILES:
        return
    if Path(rel).suffix.lower() not in CODE_SUFFIXES:
        return
    content = written_content(tool_input)
    if re.search(r"\b(" + FORBIDDEN_PACKAGES + r")\b", content, re.I) and rel.endswith(
        ("pyproject.toml", "requirements.txt", "package.json", "uv.lock")
    ):
        block(f"BLOQUEADO: {rel} declara una dependencia de evasión antibot/captcha (CLAUDE.md §3).")
    for pattern, reason in FORBIDDEN_CODE:
        if pattern.search(content):
            block(
                f"BLOQUEADO en {rel}: el código {reason}. "
                "Esto viola las reglas de cumplimiento (CLAUDE.md §3, skill cumplimiento-dian). "
                "Implementa detección + pausa asistida + estado REQUIERE_INTERVENCION_HUMANA."
            )


def main() -> None:
    event = read_event()
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    if tool == "Bash":
        check_bash(str(tool_input.get("command", "")))
    elif tool in {"Write", "Edit", "MultiEdit"}:
        check_write(tool_input)
    sys.exit(0)


if __name__ == "__main__":
    main()
