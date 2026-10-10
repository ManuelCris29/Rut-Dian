"""Espera pasiva de visibilidad (T-38, ADR-0003 §2.4).

Solo `wait_for(state="visible")` sobre localizadores de selectores validados; nunca acciones.
"""

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from rut_checker.adapters.dian_portal.locators import locate
from rut_checker.adapters.dian_portal.models import SelectorSpec


def wait_for_any_visible(page: Page, specs: list[SelectorSpec], timeout_ms: int) -> bool:
    """Espera a que alguna coincidencia VISIBLE de `specs` aparezca en el DOM principal.

    Returns:
        `True` si apareció; `False` si se agotó `timeout_ms`. El llamador reclasifica la página:
        agotar la espera no es por sí mismo un error (decisión del usuario 2026-10-10). Otros
        errores de Playwright se propagan para que los traduzca `run_translated`.
    """
    if not specs:
        return False
    combined: Locator = locate(page, specs[0])
    for spec in specs[1:]:
        combined = combined.or_(locate(page, spec))
    # `filter(visible=True)` (Playwright >= 1.51): un primer elemento oculto no cuenta, y `.first`
    # evita el error de modo estricto si hay varios visibles a la vez.
    try:
        combined.filter(visible=True).first.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return False
    return True
