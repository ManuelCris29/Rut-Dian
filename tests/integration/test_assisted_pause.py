"""Pruebas de MECANISMO de `DianPortalSource` y de la pausa asistida (T-49, ADR-0003 §3).

Fixtures sintéticos locales (D-4): no representan el portal de la DIAN y no sustituyen G3/G4 con
fixtures reales (T-48/T-51). El navegador de estas pruebas corre `headless=True` con un `launcher`
inyectado (parámetro de prueba explícito); el literal `headless=False` queda en
`source.launch_visible`, que la prueba de arquitectura exige. Cada fuente crea su propio Playwright,
por eso estas pruebas no usan las fixtures `browser`, `context` ni `page` de `conftest.py`.
"""

import contextlib
import itertools
import json
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from doubles import OperatorDouble
from playwright.sync_api import Page
from source_support import (
    CHALLENGE_JS,
    IDENT,
    RESOLVE_JS,
    RESOLVE_LATER_JS,
    Make,
    ResolvingOperator,
    cookie_names,
    evaluate,
)

from rut_checker.adapters.dian_portal.source import DianPortalSource
from rut_checker.application.retry_policy import NEVER_RETRY
from rut_checker.domain.errors import (
    HumanInterventionRequired,
    SessionExpired,
)
from rut_checker.domain.status import ChallengeEvent, QueryStatus
from rut_checker.infra.logging import ChallengeLogSink, close_run_logging, configure_logging

# --- flujo y extracción -------------------------------------------------------------------------


# --- pausa asistida -----------------------------------------------------------------------------


def test_unresolved_challenge_raises_human_intervention(make_source: Make) -> None:
    operator = OperatorDouble()
    source = make_source("desafio_inicial", operator, challenge_s=1)
    started = time.monotonic()
    with pytest.raises(HumanInterventionRequired) as caught:
        source.query(IDENT)
    assert time.monotonic() - started >= 0.9  # esperó el plazo completo antes de rendirse
    assert str(caught.value) == HumanInterventionRequired.default_message
    assert (
        operator.confirm_prompts == []
    )  # decidir si se continúa es del servicio, no del adaptador
    assert len(operator.notifications) == 1
    operator.assert_no_full_identification("1000000001")
    assert "1000000001" not in operator.notifications[0]
    assert "1 s" in operator.notifications[0]  # informa el plazo


@pytest.mark.parametrize("mode", ["desafio_inicial", "desafio_enviar"])
@pytest.mark.parametrize("resolve", [RESOLVE_JS, RESOLVE_LATER_JS], ids=["now", "later"])
def test_resolved_challenge_continues(make_source: Make, mode: str, resolve: str) -> None:
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: evaluate(holder[0], resolve))
    source = make_source(mode, operator, challenge_s=5)
    holder.append(source)
    result = source.query(IDENT)
    assert (result.status, result.estado_rut) == (QueryStatus.EXITOSA, "ESTADO-SINTETICO")
    assert len(operator.notifications) == 1


def test_second_challenge_in_the_same_query_is_not_paused_again(make_source: Make) -> None:
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: evaluate(holder[0], RESOLVE_JS))
    source = make_source("desafio_doble", operator, challenge_s=5)
    holder.append(source)
    with pytest.raises(HumanInterventionRequired):
        source.query(IDENT)
    assert len(operator.notifications) == 1  # ADR-0003 §3.4: sin segunda pausa


@pytest.mark.parametrize("mode", ["desafio_inicial", "desafio_enviar", "desafio_doble"])
def test_adapter_never_interacts_with_challenge(make_source: Make, mode: str) -> None:
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: evaluate(holder[0], RESOLVE_LATER_JS))
    source = make_source(mode, operator, challenge_s=2)
    holder.append(source)
    with contextlib.suppress(HumanInterventionRequired):
        source.query(IDENT)
    assert evaluate(source, CHALLENGE_JS) == []  # ni clics, ni foco, ni entrada, ni ratón
    focused = "document.activeElement === document.querySelector('[data-testid=desafio-sintetico]')"
    assert evaluate(source, focused) is False


def test_unresolved_challenge_keeps_the_same_context_page_and_cookies(
    make_source: Make, local_server: str
) -> None:
    source = make_source("desafio_inicial", challenge_s=1)
    context, page = source._context, source._page
    context.add_cookies([{"name": "marca_prueba", "value": "1", "url": local_server}])
    new_pages: list[Page] = []
    context.on("page", lambda opened: new_pages.append(opened))
    with pytest.raises(HumanInterventionRequired):
        source.query(IDENT)
    assert (source._context, source._page) == (context, page)
    assert new_pages == []  # ninguna página nueva ante un desafío
    assert context.pages == [page]
    assert {"marca_prueba", "sesion_sintetica"} <= cookie_names(context)  # nada se limpió


# --- sesión vencida y cierre --------------------------------------------------------------------


def test_session_expired_opens_a_new_page_in_the_same_context(
    make_source: Make, local_server: str
) -> None:
    answers = itertools.chain([True], itertools.repeat(False))
    source = make_source("ok", session_probe=lambda _page: next(answers))
    context, old_page = source._context, source._page
    context.add_cookies([{"name": "marca_prueba", "value": "1", "url": local_server}])
    with pytest.raises(SessionExpired):
        source.query(IDENT)
    assert source._context is context
    assert source._page is not old_page
    assert old_page.is_closed()
    assert context.pages == [source._page]
    assert "marca_prueba" in cookie_names(context)  # las cookies no se limpian
    assert source.query(IDENT).status is QueryStatus.EXITOSA  # el reintento usa la página nueva


def test_closed_page_is_not_retryable_human_intervention(make_source: Make) -> None:
    source = make_source("ok")
    source._page.close()
    with pytest.raises(HumanInterventionRequired) as caught:
        source.query(IDENT)
    assert isinstance(caught.value, NEVER_RETRY)
    assert source._page.is_closed()  # no se abre una página nueva (solo SessionExpired)


def test_browser_closed_during_the_wait_is_human_intervention(make_source: Make) -> None:
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: holder[0]._browser.close())
    source = make_source("desafio_inicial", operator, challenge_s=5)
    holder.append(source)
    with pytest.raises(HumanInterventionRequired) as caught:
        source.query(IDENT)
    assert isinstance(caught.value, NEVER_RETRY)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None  # sin texto de Playwright encadenado
    with pytest.raises(HumanInterventionRequired):  # el siguiente intento tampoco reintenta
        source.query(IDENT)


# --- construcción -------------------------------------------------------------------------------


# --- eventos de desafío (ADR-0003 §3.1, §3.4, §3.5; RF-07) ------------------------------------


def _recorder() -> tuple[list[tuple[ChallengeEvent, int]], Callable[[ChallengeEvent, int], None]]:
    events: list[tuple[ChallengeEvent, int]] = []
    return events, lambda event, ms: events.append((event, ms))


def test_unresolved_challenge_emits_detected_then_timeout(make_source: Make) -> None:
    events, sink = _recorder()
    source = make_source("desafio_inicial", challenge_s=1, on_challenge=sink)
    with pytest.raises(HumanInterventionRequired):
        source.query(IDENT)
    assert [event for event, _ in events] == [ChallengeEvent.DETECTED, ChallengeEvent.TIMEOUT]
    assert events[0][1] == 0
    assert events[1][1] >= 900  # ms transcurridos hasta rendirse


def test_resolved_challenge_emits_detected_then_resolved(make_source: Make) -> None:
    events, sink = _recorder()
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: evaluate(holder[0], RESOLVE_LATER_JS))
    source = make_source("desafio_inicial", operator, challenge_s=5, on_challenge=sink)
    holder.append(source)
    source.query(IDENT)
    assert [event for event, _ in events] == [ChallengeEvent.DETECTED, ChallengeEvent.RESOLVED]
    assert events[1][1] >= 200


def test_no_challenge_emits_no_events(make_source: Make) -> None:
    events, sink = _recorder()
    make_source("ok", on_challenge=sink).query(IDENT)
    assert events == []


def test_second_challenge_in_the_same_query_emits_no_extra_events(make_source: Make) -> None:
    events, sink = _recorder()
    holder: list[DianPortalSource] = []
    operator = ResolvingOperator(lambda: evaluate(holder[0], RESOLVE_JS))
    source = make_source("desafio_doble", operator, challenge_s=5, on_challenge=sink)
    holder.append(source)
    with pytest.raises(HumanInterventionRequired):
        source.query(IDENT)
    assert [event for event, _ in events] == [ChallengeEvent.DETECTED, ChallengeEvent.RESOLVED]


def test_challenge_events_reach_the_jsonl_log_without_identification(
    make_source: Make, tmp_path: Path
) -> None:
    run_id = "20261010-120000-abcd"
    sink = ChallengeLogSink()
    sink.bind(configure_logging(run_id, tmp_path))
    try:
        source = make_source("desafio_inicial", challenge_s=1, on_challenge=sink)
        with pytest.raises(HumanInterventionRequired):
            source.query(IDENT)
    finally:
        close_run_logging(run_id)
    raw = (tmp_path / f"run_{run_id}.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in raw.splitlines()]
    assert [line["event"] for line in lines] == ["challenge_detected", "challenge_timeout"]
    assert all(set(line) <= {"ts", "event", "run_id", "duration_ms"} for line in lines)
    assert lines[1]["duration_ms"] >= 900
    assert "1000000001" not in raw


# --- el desafío se oculta y reaparece -----------------------------------------------------------


def test_challenge_hidden_and_back_keeps_waiting_with_a_single_notice(make_source: Make) -> None:
    events, sink = _recorder()
    holder: list[DianPortalSource] = []
    script = "window.__ocultarYVolver(); setTimeout(window.__resolverSintetico, 900)"
    operator = ResolvingOperator(lambda: evaluate(holder[0], script))
    source = make_source("desafio_intermitente", operator, challenge_s=5, on_challenge=sink)
    holder.append(source)
    result = source.query(IDENT)
    assert (result.status, result.estado_rut) == (QueryStatus.EXITOSA, "ESTADO-SINTETICO")
    assert len(operator.notifications) == 1  # sin nuevo aviso al reaparecer
    assert [event for event, _ in events] == [ChallengeEvent.DETECTED, ChallengeEvent.RESOLVED]
    assert events[1][1] >= 800
    assert evaluate(source, CHALLENGE_JS) == []  # todo pasivo
