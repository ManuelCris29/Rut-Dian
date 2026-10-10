"""Pruebas de MECANISMO de detección de desafío y bloqueo (T-38) con fixtures sintéticos locales.

No representan el portal de la DIAN (D-4); no sustituyen G3/G4 con fixtures reales (T-48/T-51).
"""

import pytest
from playwright.sync_api import Page, Route
from portal_support import SHORT_MS, SYNTHETIC_DIR, WAIT_MS, UrlOf

from rut_checker.adapters.dian_portal.detection import (
    PageKind,
    assert_structure,
    check_page,
    find_block,
    find_challenge,
    inspect_page,
)
from rut_checker.adapters.dian_portal.models import PortalSelectors, SelectorSpec
from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
)


def _with_block_marker(selectors: PortalSelectors) -> PortalSelectors:
    marker = SelectorSpec(strategy="testid", value="bloqueo-sintetico")
    detection = selectors.detection.model_copy(
        update={"block_markers": [marker], "block_observed": None, "block_evidence": ""}
    )
    return selectors.model_copy(update={"detection": detection})


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


def test_late_challenge_is_a_challenge_not_a_timeout_nor_structure_error(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_tardio.html"))
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=WAIT_MS)


def test_challenge_still_wins_when_reclassifying_after_the_wait(
    page: Page, fixture_url: UrlOf, selectors: PortalSelectors
) -> None:
    response = page.goto(fixture_url("mecanismo_desafio_sin_resolver.html"))
    only_results = frozenset({PageKind.RESULT, PageKind.NO_RESULT})
    with pytest.raises(HumanInterventionRequired):
        check_page(page, response, selectors, timeout_ms=SHORT_MS, expected=only_results)


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
