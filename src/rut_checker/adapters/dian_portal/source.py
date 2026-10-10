"""`DianPortalSource`: consulta del portal público en navegador visible con pausa asistida (T-49).

Solo implementa el MECANISMO; los selectores reales dependen de T-14 (bloqueada). Reglas de
cumplimiento (CLAUDE.md §3, ADR-0003 §3):

- Se construye únicamente con el `EnabledPortal` de `ensure_portal_enabled` (triple llave). Los
  selectores sintéticos solo se aceptan con un servidor local (`127.0.0.1` o `localhost`).
- `headless=False` está fijo en `launch_visible`: sin `args`, sin user-agent, sin proxy ni stealth.
- Descargas desactivadas (`accept_downloads=False`). Un navegador, un contexto y una página por
  lote, creados en `_start`. Solo `SessionExpired` abre una página nueva en el mismo contexto
  (`_replace_page`); nunca se recrea el contexto ni se limpian cookies, ni siquiera ante un
  desafío o un bloqueo.
- Ante un desafío: aviso al operador y espera PASIVA (`assisted_wait`, hasta
  `HUMAN_CHALLENGE_TIMEOUT_S`) a que desaparezca; sin clics, foco ni entrada en el frame. Una sola
  pausa por consulta; los hitos van al recolector `on_challenge`. Contar bloqueos y preguntar si
  se continúa es del servicio (`BatchQueryService`, T-45).
- Un navegador o página cerrados por la persona (`TargetClosedError`) no es transitorio: se eleva a
  `HumanInterventionRequired`, que el servicio nunca reintenta (cuenta como bloqueo, y un segundo
  seguido detiene el lote). `PortalUnavailable` se reservaría para fallos reintentables.
- El ritmo entre consultas lo controla el servicio (`paced = True`), no este adaptador.
"""

from collections.abc import Callable
from contextlib import suppress
from typing import Final, NamedTuple
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    sync_playwright,
)
from playwright.sync_api import Error as PlaywrightError

from rut_checker.adapters.dian_portal.assisted_wait import ChallengeSink, wait_for_human
from rut_checker.adapters.dian_portal.detection import PageKind, check_page, run_translated
from rut_checker.adapters.dian_portal.form_flow import (
    open_form,
    read_result,
    submit_identification,
)
from rut_checker.adapters.dian_portal.selectors import EnabledPortal
from rut_checker.domain.errors import (
    HumanInterventionRequired,
    PortalUnavailable,
    SessionExpired,
    SourceNotEnabledError,
    SourceNotEnabledReason,
)
from rut_checker.domain.models import IdentificationInput, RutResult
from rut_checker.domain.status import SourceKind
from rut_checker.infra.settings import Settings, is_valid_portal_url
from rut_checker.ports.operator import OperatorPort

__all__ = [
    "DEFAULT_LAUNCHER",
    "ChallengeSink",
    "DianPortalSource",
    "Launcher",
    "SessionProbe",
    "launch_visible",
]

Launcher = Callable[[Playwright], Browser]
SessionProbe = Callable[[Page], bool]
LOCAL_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
FORM_ONLY: Final = frozenset({PageKind.FORM})
RESULT_ONLY: Final = frozenset({PageKind.RESULT, PageKind.NO_RESULT})


def launch_visible(playwright: Playwright) -> Browser:
    """Chromium VISIBLE, sin argumentos ni opciones que oculten la automatización."""
    return playwright.chromium.launch(headless=False)


# Lanzador por defecto. Las pruebas pasan otro explícitamente (`launcher=`) para correr headless
# sin tocar este módulo; el literal `headless=False` de arriba lo exige la prueba de arquitectura.
DEFAULT_LAUNCHER: Final[Launcher] = launch_visible


class _Session(NamedTuple):
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


def _is_local_http(url: str) -> bool:
    """URL `http` hacia 127.0.0.1 o localhost, sin userinfo ni caracteres de control."""
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char == "\\" for char in url):
        return False
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018  (valida el puerto)
    except ValueError:
        return False
    return parts.scheme == "http" and "@" not in parts.netloc and parts.hostname in LOCAL_HOSTS


def _resolve_url(portal: EnabledPortal, settings: Settings, base_url: str | None) -> str:
    """URL del formulario, tras exigir el token de la triple llave y un destino permitido."""
    if not isinstance(portal, EnabledPortal):
        raise SourceNotEnabledError(SourceNotEnabledReason.NOT_ENABLED_PORTAL)
    if portal.synthetic:
        if base_url is None or not _is_local_http(base_url):
            raise SourceNotEnabledError(SourceNotEnabledReason.SYNTHETIC_NOT_LOCAL)
        return base_url
    url = settings.portal_url if base_url is None else base_url
    if not is_valid_portal_url(url):
        raise SourceNotEnabledError(SourceNotEnabledReason.INVALID_URL)
    return url


def _stop(playwright: Playwright, browser: Browser | None) -> None:
    """Cierra navegador y Playwright sin propagar errores (idempotente)."""
    if browser is not None:
        with suppress(PlaywrightError):
            browser.close()
    with suppress(PlaywrightError):
        playwright.stop()


def _start(launcher: Launcher, timeout_ms: int) -> _Session:
    """Arranque del lote: navegador, ÚNICO contexto y primera página."""
    playwright = sync_playwright().start()
    browser: Browser | None = None
    try:
        browser = launcher(playwright)
        context = browser.new_context(accept_downloads=False)
        context.set_default_timeout(timeout_ms)
        page = context.new_page()
    except BaseException:
        _stop(playwright, browser)
        raise
    return _Session(playwright, browser, context, page)


class DianPortalSource:
    """Implementación de `RutSourcePort` sobre el portal público, en modo asistido."""

    def __init__(
        self,
        portal: EnabledPortal,
        settings: Settings,
        operator: OperatorPort,
        *,
        base_url: str | None = None,
        launcher: Launcher = DEFAULT_LAUNCHER,
        session_probe: SessionProbe | None = None,
        on_challenge: ChallengeSink | None = None,
    ) -> None:
        """Valida la puerta y abre el navegador.

        Args:
            portal: resultado de `ensure_portal_enabled` (único tipo aceptado).
            settings: tiempos de navegación y de espera al operador.
            operator: canal para avisar a la persona (mensajes sin identificación).
            base_url: URL del formulario. Con selectores sintéticos es obligatoria y local.
            launcher: lanzador del navegador; solo las pruebas pasan uno distinto del visible.
            session_probe: señal de sesión vencida de T-48 (con T-14 resuelta); por defecto ninguna.
            on_challenge: recolector de hitos de la pausa asistida (`DETECTED`, `RESOLVED`,
                `TIMEOUT`, con ms transcurridos); la CLI lo enlaza al log, sin identificación.

        Raises:
            SourceNotEnabledError: sin `EnabledPortal` o con una URL no permitida.
            PortalUnavailable: el navegador no pudo abrirse.
        """
        self._url = _resolve_url(portal, settings, base_url)
        self._selectors = portal.selectors
        self._operator = operator
        self._nav_ms = settings.navigation_timeout_s * 1000
        self._challenge_s = settings.human_challenge_timeout_s
        self._probe = session_probe
        self._emit = on_challenge
        self._closed = False
        session = run_translated(lambda: _start(launcher, self._nav_ms))
        self._playwright, self._browser, self._context, self._page = session

    @property
    def kind(self) -> SourceKind:
        """Origen del dato: `PORTAL_DIAN_C1`."""
        return SourceKind.PORTAL_DIAN_C1

    @property
    def paced(self) -> bool:
        """Consulta un sistema externo: aplica el ritmo (RNF-02)."""
        return True

    def query(self, ident: IdentificationInput) -> RutResult:
        """Consulta una identificación; devuelve un resultado o lanza una `RutCheckerError`.

        Raises:
            SessionExpired: ya con una página nueva en el mismo contexto (reintenta el servicio).
            HumanInterventionRequired: desafío sin resolver a tiempo, segundo desafío en la misma
                consulta, o navegador y página cerrados por la persona.
            PortalUnavailable, QueryTimeout, AccessBlocked, StructureChanged, IncompleteResult:
                ver `detection.check_page` y `form_flow.read_result`.
        """
        self._raise_if_closed()
        try:
            return self._run(ident)
        except SessionExpired:
            self._replace_page()
            raise
        except PortalUnavailable:
            if not self._target_closed():
                raise
        raise HumanInterventionRequired  # fuera del `except`: sin cadena con el error anterior

    def close(self) -> None:
        """Cierra navegador y Playwright; idempotente."""
        if not self._closed:
            self._closed = True
            _stop(self._playwright, self._browser)

    def _target_closed(self) -> bool:
        """La persona (o el sistema) cerró la página o el navegador."""
        return self._closed or self._page.is_closed() or not self._browser.is_connected()

    def _raise_if_closed(self) -> None:
        if self._target_closed():
            raise HumanInterventionRequired

    def _replace_page(self) -> None:
        """Página nueva en el MISMO contexto (único caso: `SessionExpired`); cookies intactas."""
        old = self._page
        if self._target_closed():
            return
        self._page = run_translated(self._context.new_page)
        with suppress(PlaywrightError):
            old.close()

    def _run(self, ident: IdentificationInput) -> RutResult:
        response = open_form(self._page, self._url, self._nav_ms)
        _, paused = self._settle(response, FORM_ONLY, form_url=self._url, paused=False)
        submit_identification(self._page, self._selectors, ident.identification, self._nav_ms)
        # Sin respuesta ni URL de referencia: se desconoce cómo responde el envío hasta T-14.
        kind, _ = self._settle(None, RESULT_ONLY, form_url=None, paused=paused)
        return read_result(self._page, self._selectors, kind)

    def _check(
        self, response: Response | None, expected: frozenset[PageKind], form_url: str | None
    ) -> PageKind:
        return check_page(
            self._page,
            response,
            self._selectors,
            timeout_ms=self._nav_ms,
            form_url=form_url,
            expected=expected,
        )

    def _settle(
        self,
        response: Response | None,
        expected: frozenset[PageKind],
        *,
        form_url: str | None,
        paused: bool,
    ) -> tuple[PageKind, bool]:
        """Detección completa; ante un desafío hace la pausa asistida (una vez por consulta).

        Args:
            paused: ya hubo una pausa en esta consulta; un nuevo desafío no se espera otra vez.

        Returns:
            El tipo de página reconocido y si ya hubo pausa en la consulta.
        """
        if self._probe is not None and self._probe(self._page):
            raise SessionExpired
        try:
            return self._check(response, expected, form_url), paused
        except HumanInterventionRequired:
            if paused:
                raise
        wait_for_human(
            self._page,
            self._selectors,
            expected,
            seconds=self._challenge_s,
            notify=self._operator.notify,
            emit=self._emit,
        )
        # Respuesta ya vieja (p. ej. un desafío servido con 403): se reclasifica sin ella. Si
        # aparece otro desafío no hay segunda pausa: `check_page` lanza `HumanInterventionRequired`.
        return self._check(None, expected, form_url), True
