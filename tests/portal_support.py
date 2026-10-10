"""Constantes y tipos compartidos por las pruebas del adaptador del portal (T-38)."""

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DIR = ROOT / "tests" / "fixtures" / "html" / "sintetico"
SELECTORS_FILE = ROOT / "tests" / "fixtures" / "selectors_test.yaml"


@dataclass
class BrowserGuard:
    """Registro de peticiones del navegador abortadas por no ser locales."""

    blocked: list[str] = field(default_factory=list)
    blocked_websockets: list[str] = field(default_factory=list)
    leaked: list[str] = field(default_factory=list)
