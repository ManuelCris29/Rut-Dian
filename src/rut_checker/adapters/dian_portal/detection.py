"""Detección pasiva de estado de página (T-38, ADR-0003 §2).

Orden tras cada navegación o envío: marcador de URL de mantenimiento (o URL distinta de la del
formulario), desafío, respuesta 5xx, bloqueo, elemento esperado y, si nada se reconoce,
`StructureChanged` (red de seguridad: parada segura, nunca un dato vacío). Desviación del
ADR-0003 §2: el desafío se comprueba antes del 5xx, porque un desafío servido con 503 sigue
siendo un desafío (ver el ADR).

Reglas de cumplimiento (CLAUDE.md §3):
- Solo visibilidad (`is_visible`, `wait_for`) del elemento host del desafío en el DOM principal.
  Prohibido entrar al frame, hacer clic, escribir, enfocar, pasar el ratón o evaluar código sobre
  el desafío (verificado por la prueba de arquitectura).
- No se recrea el contexto ni la página, ni se limpian cookies ante un desafío o bloqueo.
- Esperar a que una persona resuelva un desafío es responsabilidad de `DianPortalSource` (T-49),
  de forma pasiva y con `HUMAN_CHALLENGE_TIMEOUT_S`; aquí solo se detecta.
- Los errores de Playwright se traducen a dominio con mensaje genérico, sin `__cause__` ni
  `__context__`: su registro de llamadas puede contener la identificación consultada.

Pendiente T-49: `TargetClosedError` (navegador o página cerrados por la persona) hoy se traduce a
`PortalUnavailable`, que es transitorio y reintentable; no lo es. T-49 debe tratarlo aparte.
"""

from collections.abc import Callable
from enum import StrEnum
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from rut_checker.adapters.dian_portal.locators import locate
from rut_checker.adapters.dian_portal.models import PortalSelectors, SelectorSpec
from rut_checker.adapters.dian_portal.waiting import wait_for_any_visible
from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
    PortalUnavailable,
    QueryTimeout,
    RutCheckerError,
    StructureChanged,
)

__all__ = [
    "ALL_EXPECTED",
    "PageKind",
    "assert_structure",
    "check_page",
    "find_block",
    "find_challenge",
    "inspect_page",
    "is_maintenance",
    "raise_for_kind",
    "run_translated",
]

BLOCK_STATUSES = frozenset({403, 429})
SERVER_ERROR_FROM = 500


class PageKind(StrEnum):
    """Lo que la página muestra, en el orden de comprobación de ADR-0003 §2."""

    MAINTENANCE = "maintenance"
    CHALLENGE = "challenge"
    BLOCKED = "blocked"
    FORM = "form"
    RESULT = "result"
    NO_RESULT = "no_result"
    UNKNOWN = "unknown"


ALL_EXPECTED = frozenset({PageKind.FORM, PageKind.RESULT, PageKind.NO_RESULT})
# Prioridad si hay varios visibles a la vez: resultado antes que formulario.
_PRIORITY = (PageKind.RESULT, PageKind.NO_RESULT, PageKind.FORM)


def run_translated[T](action: Callable[[], T]) -> T:
    """Ejecuta `action` traduciendo errores de Playwright a dominio con mensaje genérico.

    `TimeoutError` pasa a `QueryTimeout` y cualquier otro `Error` (red, página o navegador
    cerrados) a `PortalUnavailable`. La excepción de dominio se crea y se lanza fuera del bloque
    `except`, así no queda `__context__` con el texto de Playwright (Obs-3, I-1).
    """
    error: RutCheckerError
    try:
        return action()
    except PlaywrightTimeoutError:
        error = QueryTimeout()
    except PlaywrightError:
        error = PortalUnavailable()
    raise error


def _visible(page: Page, spec: SelectorSpec) -> bool:
    """Alguna coincidencia visible en el DOM principal (sin esperar)."""
    return any(match.is_visible() for match in locate(page, spec).all())


def _any_visible(page: Page, specs: list[SelectorSpec]) -> bool:
    return any(_visible(page, spec) for spec in specs)


def _same_page(first: str, second: str) -> bool:
    """Compara esquema, host y ruta (ignora consulta, fragmento y barra final)."""
    one, two = urlsplit(first), urlsplit(second)
    return (one.scheme.lower(), one.netloc.lower(), one.path.rstrip("/")) == (
        two.scheme.lower(),
        two.netloc.lower(),
        two.path.rstrip("/"),
    )


def _url_maintenance(
    page: Page, response: Response | None, selectors: PortalSelectors, form_url: str | None
) -> bool:
    """URL final con un marcador de mantenimiento o distinta de la URL del formulario."""
    if form_url is not None and not _same_page(page.url, form_url):
        return True
    urls = [page.url.lower()]
    if response is not None:
        urls.append(response.url.lower())
    markers = [m.strip().lower() for m in selectors.detection.maintenance_url_markers if m.strip()]
    return any(marker in url for marker in markers for url in urls)


def _server_error(response: Response | None) -> bool:
    return response is not None and response.status >= SERVER_ERROR_FROM


def is_maintenance(
    page: Page,
    response: Response | None,
    selectors: PortalSelectors,
    form_url: str | None = None,
) -> bool:
    """Mantenimiento: marcador de URL, URL distinta de `form_url` (si se da) o respuesta 5xx.

    Los errores de red de `page.goto` no llegan aquí (no hay respuesta): los traduce
    `run_translated` a `PortalUnavailable`.
    """
    return _url_maintenance(page, response, selectors, form_url) or _server_error(response)


def find_challenge(page: Page, selectors: PortalSelectors) -> bool:
    """Desafío presente: algún `challenge_markers` visible en el DOM principal."""
    return _any_visible(page, selectors.detection.challenge_markers)


def find_block(page: Page, response: Response | None, selectors: PortalSelectors) -> bool:
    """Bloqueo: respuesta 403/429 o algún `block_markers` visible en el DOM principal."""
    if response is not None and response.status in BLOCK_STATUSES:
        return True
    return _any_visible(page, selectors.detection.block_markers)


def _expected_specs(
    selectors: PortalSelectors, expected: frozenset[PageKind]
) -> list[tuple[PageKind, SelectorSpec]]:
    by_kind = {
        PageKind.RESULT: selectors.result.status,
        PageKind.NO_RESULT: selectors.result.no_result_msg,
        PageKind.FORM: selectors.form.id_input,
    }
    return [(kind, by_kind[kind]) for kind in _PRIORITY if kind in expected]


def _expected_kind(
    page: Page, selectors: PortalSelectors, expected: frozenset[PageKind]
) -> PageKind:
    """Primer elemento esperado visible según la prioridad; `UNKNOWN` si ninguno lo está."""
    for kind, spec in _expected_specs(selectors, expected):
        if _visible(page, spec):
            return kind
    return PageKind.UNKNOWN


def assert_structure(
    page: Page, selectors: PortalSelectors, expected: frozenset[PageKind] = ALL_EXPECTED
) -> PageKind:
    """Exige un elemento esperado visible (sin esperar); si no hay, `StructureChanged`.

    Es la red de seguridad del ADR-0003 §2.5: una página no reconocida (incluido un desafío no
    catalogado) detiene el lote en lugar de devolver un dato vacío o reintentar a ciegas.
    """
    kind = run_translated(lambda: _expected_kind(page, selectors, expected))
    if kind is PageKind.UNKNOWN:
        raise StructureChanged
    return kind


def _static_kind(
    page: Page, response: Response | None, selectors: PortalSelectors, form_url: str | None
) -> PageKind | None:
    """Mantenimiento por URL, desafío, 5xx y bloqueo; `None` si ninguno aplica."""
    if _url_maintenance(page, response, selectors, form_url):
        return PageKind.MAINTENANCE
    if find_challenge(page, selectors):
        return PageKind.CHALLENGE
    if _server_error(response):
        return PageKind.MAINTENANCE
    if find_block(page, response, selectors):
        return PageKind.BLOCKED
    return None


def inspect_page(
    page: Page,
    response: Response | None,
    selectors: PortalSelectors,
    *,
    form_url: str | None = None,
    expected: frozenset[PageKind] = ALL_EXPECTED,
) -> PageKind:
    """Clasifica la página sin esperar y sin lanzar excepciones de dominio (salvo Playwright)."""

    def classify() -> PageKind:
        return _static_kind(page, response, selectors, form_url) or _expected_kind(
            page, selectors, expected
        )

    return run_translated(classify)


def raise_for_kind(kind: PageKind) -> PageKind:
    """Convierte las clases no esperadas en la excepción de dominio que corresponde."""
    match kind:
        case PageKind.MAINTENANCE:
            raise PortalUnavailable
        case PageKind.CHALLENGE:
            raise HumanInterventionRequired
        case PageKind.BLOCKED:
            raise AccessBlocked
        case PageKind.UNKNOWN:
            raise StructureChanged
        case _:
            return kind


def check_page(
    page: Page,
    response: Response | None,
    selectors: PortalSelectors,
    *,
    timeout_ms: int,
    form_url: str | None = None,
    expected: frozenset[PageKind] = ALL_EXPECTED,
) -> PageKind:
    """Detección completa en el orden del ADR-0003 §2.

    Si el estado no es concluyente (sin mantenimiento, desafío ni bloqueo), espera de forma pasiva
    hasta `timeout_ms` a que aparezca un elemento esperado, un desafío o un bloqueo, y vuelve a
    clasificar. Con `timeout_ms=0` no espera (la página ya está cargada).

    Args:
        timeout_ms: espera máxima; la fija quien llama (p. ej. `RUT_NAVIGATION_TIMEOUT_S`).
        form_url: URL del formulario; si la URL final es otra se considera mantenimiento.
        expected: elementos que se esperan en este paso (p. ej. solo resultado tras enviar).

    Returns:
        `FORM`, `RESULT` o `NO_RESULT` (los que estén en `expected`).

    Raises:
        PortalUnavailable: mantenimiento, 5xx o red.
        HumanInterventionRequired: desafío visible, también si aparece durante la espera.
        AccessBlocked: 403/429 o marcador de bloqueo.
        StructureChanged: tras la espera (o sin ella) no hay ningún elemento esperado visible;
            incluye un tipo no esperado (p. ej. el formulario otra vez tras enviar).

    `DianPortalSource` usa `inspect_page` cuando debe pausar ante un desafío.
    """
    static = run_translated(lambda: _static_kind(page, response, selectors, form_url))
    if static is not None:
        return raise_for_kind(static)
    if timeout_ms > 0:
        detection = selectors.detection
        specs = [spec for _, spec in _expected_specs(selectors, expected)]
        specs += [*detection.challenge_markers, *detection.block_markers]
        # Agotar la espera no lanza: se reclasifica abajo (desafío/bloqueo ganan; si no se
        # reconoce nada, StructureChanged). QueryTimeout queda para goto, fill o carga.
        run_translated(lambda: wait_for_any_visible(page, specs, timeout_ms))
    return raise_for_kind(
        inspect_page(page, response, selectors, form_url=form_url, expected=expected)
    )
