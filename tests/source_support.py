"""Utilidades de las pruebas de `DianPortalSource` (T-49): navegador de prueba y operador."""

from collections.abc import Callable
from typing import Any

from doubles import OperatorDouble
from playwright.sync_api import Browser, BrowserContext, Playwright
from portal_support import HOST_RESOLVER_ARGS

from rut_checker.adapters.dian_portal.source import DianPortalSource
from rut_checker.domain.models import IdentificationInput
from rut_checker.infra.settings import Settings

IDENT = IdentificationInput(identification="1000000001")
CHALLENGE_JS = "window.__eventosDesafio"
RESOLVE_JS = "window.__resolverSintetico()"
RESOLVE_LATER_JS = "setTimeout(window.__resolverSintetico, 300)"
Make = Callable[..., DianPortalSource]


def headless_guarded(playwright: Playwright) -> Browser:
    """Solo pruebas: Chromium headless sin salida a hosts no locales."""
    return playwright.chromium.launch(headless=True, args=HOST_RESOLVER_ARGS)


def make_settings(challenge_s: int = 1) -> Settings:
    base = Settings(_env_file=None)
    # model_copy no valida: permite un timeout corto (< 30 s del validador) solo en pruebas.
    return base.model_copy(
        update={"human_challenge_timeout_s": challenge_s, "navigation_timeout_s": 5}
    )


class ResolvingOperator(OperatorDouble):
    """Doble que ejecuta una acción de prueba al recibir el aviso (simula a la persona)."""

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self._action = action

    def notify(self, message: str) -> None:
        super().notify(message)
        self._action()


def evaluate(source: DianPortalSource, expression: str) -> Any:
    return source._page.evaluate(expression)


def cookie_names(context: BrowserContext) -> set[str]:
    return {cookie["name"] for cookie in context.cookies()}
