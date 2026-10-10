"""Pasos de formulario del portal (T-49): abrir, diligenciar, enviar y leer el resultado.

Junto con `source.py`, es el único módulo que actúa sobre la página, y solo con `goto`, `fill` y
`click` sobre los selectores de formulario ya validados (la prueba de arquitectura lo exige). Nunca
se actúa sobre el desafío de seguridad: antes de cada paso, `check_page` ya descartó que esté
presente (ADR-0003 §3).

Se extraen SOLO los campos de SPEC §5 que ofrece el portal: estado del RUT y nombre o razón social.
Cualquier otro texto visible se ignora. Todo error de Playwright pasa por `run_translated`.
"""

from playwright.sync_api import Page, Response

from rut_checker.adapters.dian_portal.detection import PageKind, run_translated
from rut_checker.adapters.dian_portal.locators import locate, locate_unique
from rut_checker.adapters.dian_portal.models import PortalSelectors, SelectorSpec
from rut_checker.domain.errors import StructureChanged
from rut_checker.domain.models import RutResult
from rut_checker.domain.status import QueryStatus, SourceKind

# Un campo del portal más largo que esto no es un estado ni un nombre: el portal cambió.
MAX_FIELD_CHARS = 500


def open_form(page: Page, url: str, timeout_ms: int) -> Response | None:
    """Navega a la URL del formulario; los errores de red o de tiempo pasan a dominio."""
    return run_translated(lambda: page.goto(url, timeout=timeout_ms))


def submit_identification(
    page: Page, selectors: PortalSelectors, identification: str, timeout_ms: int
) -> None:
    """Escribe la identificación (solo dígitos, ya validada) y pulsa el botón de enviar.

    Raises:
        StructureChanged: si el campo o el botón no son únicos y visibles en el DOM principal.
    """

    def act() -> None:
        locate_unique(page, selectors.form.id_input).fill(identification, timeout=timeout_ms)
        locate_unique(page, selectors.form.submit_button).click(timeout=timeout_ms)

    run_translated(act)


def _text_of(page: Page, spec: SelectorSpec) -> str:
    """Texto visible de un único elemento, con espacios normalizados."""
    text = run_translated(lambda: locate_unique(page, spec).inner_text())
    clean = " ".join(text.split())
    if len(clean) > MAX_FIELD_CHARS:
        raise StructureChanged
    return clean


def _name_of(page: Page, selectors: PortalSelectors) -> str:
    """Nombre o razón social; vacío solo si el selector es opcional y el elemento no existe."""
    spec = selectors.result.name
    if spec is None:
        return ""
    if not spec.required and run_translated(lambda: locate(page, spec).count()) == 0:
        return ""
    return _text_of(page, spec)


def read_result(page: Page, selectors: PortalSelectors, kind: PageKind) -> RutResult:
    """Convierte la página de resultado en `RutResult` (solo SPEC §5).

    Raises:
        StructureChanged: campo obligatorio ausente, repetido o desmesurado.
        IncompleteResult: el estado existe pero está vacío (lo lanza el modelo de dominio).
    """
    if kind is PageKind.NO_RESULT:
        return RutResult(status=QueryStatus.SIN_RESULTADOS, source=SourceKind.PORTAL_DIAN_C1)
    if kind is not PageKind.RESULT:
        raise StructureChanged
    return RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.PORTAL_DIAN_C1,
        estado_rut=_text_of(page, selectors.result.status),
        name=_name_of(page, selectors),
    )
