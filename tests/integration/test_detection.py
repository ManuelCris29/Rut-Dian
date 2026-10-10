"""Pruebas de MECANISMO de detección (T-38) con fixtures sintéticos locales.

No representan el portal de la DIAN (D-4): los marcadores reales dependen de T-14 y estas
pruebas no sustituyen G3/G4 con fixtures reales (T-48/T-51).
"""

import re
import socket
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, Route
from portal_support import SYNTHETIC_DIR, BrowserGuard

from rut_checker.adapters.dian_portal.detection import (
    PageKind,
    assert_structure,
    check_page,
    find_block,
    find_challenge,
    inspect_page,
    is_maintenance,
    run_translated,
)
from rut_checker.adapters.dian_portal.locators import locate_unique
from rut_checker.adapters.dian_portal.models import PortalSelectors, SelectorSpec
from rut_checker.adapters.dian_portal.selectors import EnabledPortal
from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
    PortalUnavailable,
    QueryTimeout,
    StructureChanged,
)

UrlOf = Callable[[str], str]
SYNTHETIC_HEADER = "SINTÉTICO — no representa el portal de la DIAN"
WAIT_MS = 5000
SHORT_MS = 300


@pytest.fixture
def selectors(enabled_portal: EnabledPortal) -> PortalSelectors:
    return enabled_portal.selectors


def _with_block_marker(selectors: PortalSelectors) -> PortalSelectors:
    marker = SelectorSpec(strategy="testid", value="bloqueo-sintetico")
    detection = selectors.detection.model_copy(
        update={"block_markers": [marker], "block_observed": None, "block_evidence": ""}
    )
    return selectors.model_copy(update={"detection": detection})


def _with_url_marker(selectors: PortalSelectors, marker: str) -> PortalSelectors:
    detection = selectors.detection.model_copy(update={"maintenance_url_markers": [marker]})
    return selectors.model_copy(update={"detection": detection})


def _closed_local_port() -> int:
    """Puerto efímero que se abre y se cierra: nadie escucha en él."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_redirect_to_maintenance_image_is_unavailable(
    page: Page, local_server: str, selectors: PortalSelectors
) -> None:
    # Comportamiento observado el 2026-10-09: 302 hacia Mantenimiento-Consulta-RUT.jpg.
    response = page.goto(f"{local_server}/redirige-a-mantenimiento")
    assert response is not None
    assert page.url.endswith("Mantenimiento-Consulta-RUT.jpg")
    observed = _with_url_marker(selectors, "Mantenimiento-Consulta-RUT.jpg")
    assert is_maintenance(page, response, observed)
    with pytest.raises(PortalUnavailable):
        check_page(page, response, observed, timeout_ms=SHORT_MS)
    # Con el marcador sintético (otro texto) la redirección no se reconoce como mantenimiento.
    assert not is_maintenance(page, response, selectors)


def test_final_url_other_than_form_url_is_unavailable(
    page: Page, local_server: str, selectors: PortalSelectors
) -> None:
    form_url = f"{local_server}/redirige-a-otra-ruta"
    response = page.goto(form_url)  # termina en /html/mecanismo_formulario.html
    assert response is not None
    assert not is_maintenance(page, response, selectors)  # sin form_url no hay comparación
    assert is_maintenance(page, response, selectors, form_url=form_url)
    with pytest.raises(PortalUnavailable):
        check_page(page, response, selectors, timeout_ms=SHORT_MS, form_url=form_url)


def test_final_url_equal_to_form_url_is_not_maintenance(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    url = fixture_url("mecanismo_formulario.html")
    response = page.goto(url)
    assert not is_maintenance(page, response, selectors, form_url=url)
    kind = check_page(page, response, selectors, timeout_ms=WAIT_MS, form_url=url)
    assert kind is PageKind.FORM


def test_http_5xx_is_unavailable(page: Page, local_server: str, selectors: PortalSelectors) -> None:
    response = page.goto(f"{local_server}/estado/503")
    assert response is not None
    assert is_maintenance(page, response, selectors)
    with pytest.raises(PortalUnavailable):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)


def test_challenge_served_with_5xx_is_a_challenge(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    # Desviación documentada en ADR-0003: marcador de URL, desafío y después 5xx.
    body = (SYNTHETIC_DIR / "mecanismo_desafio_sin_resolver.html").read_text(encoding="utf-8")

    def serve_503(route: Route) -> None:
        route.fulfill(status=503, content_type="text/html; charset=utf-8", body=body)

    page.route("**/html/desafio_con_503.html", serve_503)
    response = page.goto(fixture_url("desafio_con_503.html"))
    assert response is not None
    assert response.status == 503
    assert inspect_page(page, response, selectors) is PageKind.CHALLENGE
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)


@pytest.mark.parametrize("status", [403, 429])
def test_http_403_or_429_is_access_blocked(
    page: Page, local_server: str, selectors: PortalSelectors, status: int
) -> None:
    response = page.goto(f"{local_server}/estado/{status}")
    assert response is not None
    assert not is_maintenance(page, response, selectors)
    assert find_block(page, response, selectors)
    with pytest.raises(AccessBlocked):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)


def test_non_numeric_status_path_answers_400(page: Page, local_server: str) -> None:
    response = page.goto(f"{local_server}/estado/abc")
    assert response is not None
    assert response.status == 400


def test_network_failure_becomes_portal_unavailable(page: Page) -> None:
    port = _closed_local_port()
    with pytest.raises(PortalUnavailable) as caught:
        run_translated(lambda: page.goto(f"http://127.0.0.1:{port}/"))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_browser_guard_aborts_non_local_requests(page: Page, browser_guard: BrowserGuard) -> None:
    with pytest.raises(PortalUnavailable):
        run_translated(lambda: page.goto("http://ejemplo.invalid/"))
    assert browser_guard.blocked == ["http"]


def test_browser_guard_blocks_images_websockets_and_prefetch(
    page: Page, fixture_url: UrlOf, browser_guard: BrowserGuard
) -> None:
    page.goto(fixture_url("mecanismo_recursos_externos.html"))
    page.wait_for_function("window.__wsListo === true", timeout=WAIT_MS)
    assert "http" in browser_guard.blocked  # la imagen .invalid fue abortada por el guard
    assert browser_guard.blocked_websockets == ["ws"]  # el WebSocket no local se cerró
    assert browser_guard.leaked == []  # ninguna petición no local llegó a terminar


def test_unknown_page_raises_structure_changed(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desconocido.html"))
    assert inspect_page(page, response, selectors) is PageKind.UNKNOWN
    with pytest.raises(StructureChanged):
        assert_structure(page, selectors)
    with pytest.raises(StructureChanged):
        check_page(page, response, selectors, timeout_ms=0)  # 0: sin espera, ya cargada


def test_unknown_page_after_wait_is_structure_changed(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    # Decisión del usuario 2026-10-10: agotada la espera pasiva se reclasifica; si no se reconoce
    # nada es ESTRUCTURA_CAMBIADA (sin reintento ciego), nunca QueryTimeout.
    response = page.goto(fixture_url("mecanismo_desconocido.html"))
    with pytest.raises(StructureChanged):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("mecanismo_formulario.html", PageKind.FORM),
        ("mecanismo_resultado.html", PageKind.RESULT),
        ("mecanismo_sin_resultado.html", PageKind.NO_RESULT),
    ],
)
def test_expected_pages_are_recognized(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors, name: str, kind: PageKind
) -> None:
    response = page.goto(fixture_url(name))
    assert check_page(page, response, selectors, timeout_ms=WAIT_MS) is kind
    assert assert_structure(page, selectors) is kind


def test_result_wins_over_form_when_both_are_visible(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_formulario_y_resultado.html"))
    assert check_page(page, response, selectors, timeout_ms=WAIT_MS) is PageKind.RESULT
    only_form = frozenset({PageKind.FORM})
    assert assert_structure(page, selectors, expected=only_form) is PageKind.FORM
    only_results = frozenset({PageKind.RESULT, PageKind.NO_RESULT})
    kind = check_page(page, response, selectors, timeout_ms=WAIT_MS, expected=only_results)
    assert kind is PageKind.RESULT


def test_expected_set_excludes_other_visible_elements(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_formulario.html"))
    only_results = frozenset({PageKind.RESULT, PageKind.NO_RESULT})
    with pytest.raises(StructureChanged):
        assert_structure(page, selectors, expected=only_results)
    with pytest.raises(StructureChanged):  # formulario visible otra vez tras enviar
        check_page(page, response, selectors, timeout_ms=SHORT_MS, expected=only_results)


def test_late_result_is_awaited_passively(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_resultado_tardio.html"))
    assert inspect_page(page, response, selectors) is PageKind.UNKNOWN  # aún no aparece
    kind = check_page(page, response, selectors, timeout_ms=WAIT_MS)
    assert kind is PageKind.RESULT


def test_late_challenge_is_a_challenge_not_a_timeout_nor_structure_error(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_tardio.html"))
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=WAIT_MS)


def test_presence_uses_any_visible_match_not_only_the_first(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_duplicado.html"))
    # El primer elemento está oculto y el segundo visible: hay presencia.
    assert inspect_page(page, response, selectors) is PageKind.RESULT


def test_wait_ignores_hidden_first_match(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_duplicado.html"))
    assert check_page(page, response, selectors, timeout_ms=WAIT_MS) is PageKind.RESULT


def test_challenge_still_wins_when_reclassifying_after_the_wait(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_sin_resolver.html"))
    only_results = frozenset({PageKind.RESULT, PageKind.NO_RESULT})
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=SHORT_MS, expected=only_results)


def test_locate_unique_rejects_multiple_matches(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    page.goto(fixture_url("mecanismo_duplicado.html"))
    with pytest.raises(StructureChanged):
        locate_unique(page, selectors.result.status)
    page.goto(fixture_url("mecanismo_resultado.html"))
    assert locate_unique(page, selectors.result.status).is_visible()
    with pytest.raises(StructureChanged):  # cero coincidencias
        locate_unique(page, selectors.form.id_input)


def test_synthetic_challenge_host_is_detected(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_sin_resolver.html"))
    assert find_challenge(page, selectors)
    assert inspect_page(page, response, selectors) is PageKind.CHALLENGE
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)


def test_detection_never_interacts_with_the_challenge(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_sin_resolver.html"))
    for _ in range(3):
        assert inspect_page(page, response, selectors) is PageKind.CHALLENGE
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=SHORT_MS)
    assert page.evaluate("window.__eventosDesafio") == []  # registro de clics/foco/entrada


def test_challenge_is_checked_before_block_status(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    # Orden ADR-0003: un desafío servido con 403 sigue siendo desafío, no bloqueo.
    body = (SYNTHETIC_DIR / "mecanismo_desafio_sin_resolver.html").read_text(encoding="utf-8")

    def serve_403(route: Route) -> None:
        route.fulfill(status=403, content_type="text/html; charset=utf-8", body=body)

    page.route("**/html/otro_desafio.html", serve_403)
    response = page.goto(fixture_url("otro_desafio.html"))
    assert response is not None
    assert response.status == 403
    assert inspect_page(page, response, selectors) is PageKind.CHALLENGE


def test_resolved_challenge_lets_the_form_appear(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    page.goto(fixture_url("mecanismo_desafio_resuelto.html"))
    assert find_challenge(page, selectors)
    # La persona "resuelve" el desafío: la prueba dispara la función, sin tocar el desafío.
    page.evaluate("window.__resolverSintetico()")
    page.get_by_test_id("campo-id-sintetico").wait_for(state="visible", timeout=WAIT_MS)  # pasivo
    assert not find_challenge(page, selectors)
    assert assert_structure(page, selectors) is PageKind.FORM


def test_block_markers_are_detected_when_configured(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_bloqueo.html"))
    assert not find_block(page, response, selectors)  # sin marcadores configurados
    with_marker = _with_block_marker(selectors)
    assert find_block(page, response, with_marker)
    with pytest.raises(AccessBlocked):
        check_page(page, response, with_marker, timeout_ms=SHORT_MS)


def test_playwright_timeout_in_fill_becomes_generic_query_timeout(
    page: Page, fixture_url: UrlOf
) -> None:
    page.goto(fixture_url("mecanismo_desconocido.html"))
    field = page.get_by_test_id("campo-id-sintetico")
    with pytest.raises(QueryTimeout) as caught:
        run_translated(lambda: field.fill("1000000001", timeout=200))
    message = str(caught.value)
    assert "1000000001" not in message
    assert "fill" not in message
    assert message == QueryTimeout.default_message
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None  # sin texto de Playwright (call log) encadenado


def test_synthetic_fixtures_have_header_and_no_vendor_markers() -> None:
    files = sorted(SYNTHETIC_DIR.glob("mecanismo_*.html"))
    assert len(files) == 12
    forbidden = ("cf-turnstile", "g-recaptcha", "recaptcha", "turnstile", "cloudflare", "dian")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert f"<!-- {SYNTHETIC_HEADER} -->" in text, path.name
        assert f'<p data-testid="cabecera-sintetico">{SYNTHETIC_HEADER}</p>' in text, path.name
        body = text.replace(SYNTHETIC_HEADER, "").lower()
        assert not any(marker in body for marker in forbidden), path.name
        assert set(re.findall(r"\d{6,}", body)) <= {"1000000001"}, path.name
