"""Flujo, extracción y construcción de `DianPortalSource` (T-49) sobre fixtures sintéticos.

No representan el portal de la DIAN (D-4). Ver `test_assisted_pause.py` para la pausa asistida.
"""

from collections.abc import Callable
from typing import Any, cast

import pytest
from doubles import OperatorDouble
from playwright.sync_api import Browser, Playwright
from source_support import (
    IDENT,
    Make,
    evaluate,
    headless_guarded,
    make_settings,
)

from rut_checker.adapters.dian_portal.selectors import EnabledPortal
from rut_checker.adapters.dian_portal.source import DEFAULT_LAUNCHER, DianPortalSource
from rut_checker.domain.errors import (
    IncompleteResult,
    PortalUnavailable,
    RutCheckerError,
    SourceNotEnabledError,
    SourceNotEnabledReason,
    StructureChanged,
)
from rut_checker.domain.status import QueryStatus, SourceKind


def test_ok_flow_extracts_only_spec_fields(make_source: Make) -> None:
    source = make_source("ok")
    result = source.query(IDENT)
    assert source.kind is SourceKind.PORTAL_DIAN_C1
    assert source.paced is True
    assert (result.status, result.source) == (QueryStatus.EXITOSA, SourceKind.PORTAL_DIAN_C1)
    assert (result.estado_rut, result.name) == ("ESTADO-SINTETICO", "PERSONA FICTICIA UNO")
    assert result.observation == ""
    # El dato adicional visible en la página no se extrae (SPEC §5).
    assert "EXTRA-SINTETICO" not in result.model_dump_json()
    assert evaluate(source, "window.__envios") == ["1000000001"]


def test_no_result_page_is_sin_resultados(make_source: Make) -> None:
    result = make_source("sin").query(IDENT)
    assert result.status is QueryStatus.SIN_RESULTADOS
    assert (result.estado_rut, result.name) == ("", "")


def test_optional_name_may_be_absent(make_source: Make) -> None:
    result = make_source("sin_nombre").query(IDENT)
    assert (result.status, result.estado_rut, result.name) == (
        QueryStatus.EXITOSA,
        "ESTADO-SINTETICO",
        "",
    )


def test_blank_required_status_is_incomplete_result(make_source: Make) -> None:
    with pytest.raises(IncompleteResult):
        make_source("estado_vacio").query(IDENT)


@pytest.mark.parametrize("mode", ["sin_estado", "estado_duplicado"])
def test_missing_or_ambiguous_required_field_is_structure_changed(
    make_source: Make, mode: str
) -> None:
    with pytest.raises(StructureChanged):
        make_source(mode).query(IDENT)


def test_maintenance_redirect_is_portal_unavailable_not_human_intervention(
    make_source: Make,
) -> None:
    source = make_source(path="/redirige-a-mantenimiento")
    with pytest.raises(PortalUnavailable):
        source.query(IDENT)


def test_two_queries_reuse_the_same_page_and_context(make_source: Make) -> None:
    source = make_source("ok")
    context, page = source._context, source._page
    source.query(IDENT)
    source.query(IDENT)
    assert (source._context, source._page) == (context, page)
    assert context.pages == [page]


def test_close_is_idempotent(make_source: Make) -> None:
    source = make_source("ok")
    source.close()
    source.close()
    assert not source._browser.is_connected()


def _launch_spy() -> tuple[Callable[[Playwright], Browser], list[int]]:
    calls: list[int] = []

    def launcher(playwright: Playwright) -> Browser:
        calls.append(1)
        return headless_guarded(playwright)

    return launcher, calls


def _build(portal: object, base_url: str | None, launcher: Any) -> DianPortalSource:
    # El objetivo es probar el rechazo de lo que NO es un EnabledPortal.
    return DianPortalSource(
        cast("EnabledPortal", portal),
        make_settings(),
        OperatorDouble(),
        base_url=base_url,
        launcher=launcher,
    )


def _assert_rejected(portal: object, base_url: str | None, reason: SourceNotEnabledReason) -> None:
    launcher, calls = _launch_spy()
    with pytest.raises(SourceNotEnabledError) as caught:
        _build(portal, base_url, launcher)
    assert caught.value.reason is reason
    assert calls == []  # el navegador no se abre


def test_rejects_anything_that_is_not_an_enabled_portal() -> None:
    _assert_rejected(object(), "http://127.0.0.1:1/", SourceNotEnabledReason.NOT_ENABLED_PORTAL)


@pytest.mark.parametrize(
    "base_url",
    [None, "https://muisca.dian.gov.co/x", "http://127.0.0.2:8000/", "http://ejemplo.invalid/"],
)
def test_synthetic_selectors_require_a_local_base_url(
    enabled_portal: EnabledPortal, base_url: str | None
) -> None:
    _assert_rejected(enabled_portal, base_url, SourceNotEnabledReason.SYNTHETIC_NOT_LOCAL)


def test_real_selectors_reject_a_local_or_foreign_base_url(enabled_portal: EnabledPortal) -> None:
    real = object.__new__(EnabledPortal)  # sin token: solo para probar la rama no sintética
    object.__setattr__(real, "_selectors", enabled_portal.selectors)
    object.__setattr__(real, "_synthetic", False)
    for url in ("http://127.0.0.1:8000/", "https://evil.example.com/"):
        _assert_rejected(real, url, SourceNotEnabledReason.INVALID_URL)


def test_default_launcher_is_the_visible_one() -> None:
    assert DEFAULT_LAUNCHER.__name__ == "launch_visible"


def test_errors_raised_by_the_source_are_domain_errors(make_source: Make) -> None:
    with pytest.raises(RutCheckerError):
        make_source("sin_estado").query(IDENT)
