"""Traducción de un `SelectorSpec` a un `Locator` de Playwright (T-38).

Rol, etiqueta, texto y testid antes que CSS (skill playwright-rpa). Los valores salen siempre de
`selectors.yaml`, ya validados por `models.SelectorSpec` (sin sintaxis de motores internos ni
encadenado `>>`); este módulo no contiene ninguno.

- `locate`: todas las coincidencias. Para detección de presencia (`any` visible).
- `locate_unique`: exactamente una coincidencia; para la extracción (T-48/T-49), donde una
  coincidencia múltiple o nula en un selector obligatorio es un cambio del portal.
"""

from typing import Any, cast

from playwright.sync_api import Locator, Page

from rut_checker.adapters.dian_portal.models import SelectorSpec
from rut_checker.domain.errors import StructureChanged


def locate(page: Page, spec: SelectorSpec) -> Locator:
    """Devuelve el localizador de `spec` (todas las coincidencias) en el DOM principal."""
    match spec.strategy:
        case "label":
            return page.get_by_label(spec.value)
        case "role":
            # Any: `get_by_role` exige un Literal con todos los roles ARIA que Playwright no
            # exporta como tipo; `models.ARIA_ROLES` ya validó el valor al cargar.
            return page.get_by_role(cast("Any", spec.role), name=spec.name or None)
        case "text":
            return page.get_by_text(spec.value)
        case "testid":
            return page.get_by_test_id(spec.value)
        case "css":
            return page.locator(spec.value)


def locate_unique(page: Page, spec: SelectorSpec) -> Locator:
    """Como `locate`, pero exige exactamente una coincidencia.

    Raises:
        StructureChanged: con cero o varias coincidencias (el selector dejó de ser unívoco).
    """
    found = locate(page, spec)
    if found.count() != 1:
        raise StructureChanged
    return found
