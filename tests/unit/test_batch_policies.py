"""Políticas del lote (T-45): ritmo, reintentos con backoff, circuito, paradas y operador."""

import json
import logging
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from doubles import FakeSleeper, FixedClock, OperatorDouble

from rut_checker.adapters.contingency_source import ContingencySource
from rut_checker.adapters.document_copy_source import DocumentCopySource
from rut_checker.adapters.fake_source import FakeSource, Programmed
from rut_checker.application.batch_service import BatchQueryService
from rut_checker.application.report import BatchReport, StopReason
from rut_checker.application.retry_policy import BackoffRetryPolicy, RetryPolicy
from rut_checker.application.run_log import EVENT_NAMES
from rut_checker.domain.errors import (
    AccessBlocked,
    ExportError,
    HumanInterventionRequired,
    IncompleteResult,
    InvalidIdentification,
    InvalidReason,
    PortalUnavailable,
    QueryTimeout,
    RutCheckerError,
    SessionExpired,
    StructureChanged,
)
from rut_checker.domain.models import InputRow, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.infra.logging import LogEvent, close_logging, configure_logging
from rut_checker.infra.settings import Settings
from rut_checker.ports.rut_source import RutSourcePort

IDS = ("1000000001", "1000000002", "1000000003", "1000000004", "1000000005")
RUN_ID = "20261009-120000-abcd"
TODAY = date(2026, 10, 9)
SECURITY_NOTE = "Lote detenido: verificación de seguridad no resuelta"


@dataclass
class Harness:
    service: BatchQueryService
    source: FakeSource
    operator: OperatorDouble
    sleeper: FakeSleeper
    log_path: Path

    def log_events(self) -> list[dict[str, object]]:
        text = self.log_path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]

    def event_names(self) -> list[object]:
        return [e["event"] for e in self.log_events()]


@pytest.fixture
def logger(tmp_path: Path) -> Iterator[logging.Logger]:
    run_logger = configure_logging(RUN_ID, tmp_path)
    yield run_logger
    close_logging(run_logger)


@pytest.fixture
def make(logger: logging.Logger, tmp_path: Path) -> Callable[..., Harness]:
    def factory(
        responses: Mapping[str, Programmed],
        *,
        confirmations: tuple[bool, ...] = (),
        policy: RetryPolicy | None = None,
        fallback: RutSourcePort | None = None,
        paced: bool = True,
        min_delay: float = 5.0,
    ) -> Harness:
        settings = Settings(_env_file=None, min_delay_between_queries_s=min_delay)
        source = FakeSource(responses, paced=paced)
        operator = OperatorDouble(confirmations)
        sleeper = FakeSleeper()
        service = BatchQueryService(
            source,
            fallback or ContingencySource(),
            operator,
            FixedClock.on(TODAY),
            sleeper,
            settings,
            logger,
            retry_policy=policy or BackoffRetryPolicy.from_settings(settings),
        )
        return Harness(service, source, operator, sleeper, tmp_path / f"run_{RUN_ID}.jsonl")

    return factory


def _rows(count: int) -> list[InputRow]:
    return [InputRow(row_index=i, raw_identification=IDS[i]) for i in range(count)]


def _statuses(report: BatchReport) -> list[QueryStatus]:
    return [outcome.result.status for outcome in report.outcomes]


def _ok() -> RutResult:
    return RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.FAKE,
        estado_rut="ACTIVO",
        name="PERSONA FICTICIA UNO",
    )


def _no_results() -> RutResult:
    return RutResult(status=QueryStatus.SIN_RESULTADOS, source=SourceKind.FAKE)


PENDING = QueryStatus.PENDIENTE_VALIDACION_MANUAL
BLOCKED = QueryStatus.REQUIERE_INTERVENCION_HUMANA


# --- RetryPolicy.from_settings --------------------------------------------------------------


class _Cfg:
    def __init__(self, max_retries: int, retry_backoff_s: tuple[int, ...]) -> None:
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s


def test_from_settings_reads_the_real_settings() -> None:
    policy = BackoffRetryPolicy.from_settings(Settings(_env_file=None))
    assert policy.delay_before_retry(PortalUnavailable(), 1) == 30
    assert policy.delay_before_retry(PortalUnavailable(), 2) == 120
    assert policy.delay_before_retry(PortalUnavailable(), 3) is None


def test_portal_and_timeout_use_backoff_and_respect_max_retries() -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(1, (30, 120)))
    for error in (PortalUnavailable(), QueryTimeout()):
        assert policy.delay_before_retry(error, 1) == 30
        assert policy.delay_before_retry(error, 2) is None


def test_zero_max_retries_disables_every_retry() -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(0, (30, 120)))
    for error in (PortalUnavailable(), QueryTimeout(), SessionExpired()):
        assert policy.delay_before_retry(error, 1) is None


def test_session_expired_is_retried_exactly_once() -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(2, (30, 120)))
    assert policy.delay_before_retry(SessionExpired(), 1) == 0.0
    assert policy.delay_before_retry(SessionExpired(), 2) is None


def test_missing_backoff_values_mean_no_retry() -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(2, ()))
    assert policy.delay_before_retry(PortalUnavailable(), 1) is None


@pytest.mark.parametrize(
    "error",
    [
        HumanInterventionRequired(),
        AccessBlocked(),
        StructureChanged(),
        IncompleteResult(),
        InvalidIdentification(InvalidReason.EMPTY),
    ],
)
def test_policy_itself_never_retries_forbidden_errors(error: RutCheckerError) -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(2, (30, 120)))
    assert policy.delay_before_retry(error, 1) is None


# --- Portal no disponible: reintentos, circuito y respaldo (G5) -----------------------------


def test_maintenance_retries_then_falls_back_to_pending(make: Callable[..., Harness]) -> None:
    h = make({i: PortalUnavailable for i in IDS})
    report = h.service.run(_rows(3))
    assert _statuses(report) == [PENDING] * 3
    assert all(o.result.source is SourceKind.CONTINGENCIA_MANUAL for o in report.outcomes)
    assert h.sleeper.sleeps == [5.0, 30.0, 120.0]  # ritmo inicial y luego el backoff
    assert h.source.total_calls == 3  # solo la fila 1, con sus 3 intentos
    assert report.stop_reason is StopReason.PORTAL_UNAVAILABLE
    assert "Lote detenido" in report.outcomes[0].result.observation


def test_portal_recovering_on_retry_does_not_open_circuit(make: Callable[..., Harness]) -> None:
    h = make({IDS[0]: [PortalUnavailable, _ok()]})
    report = h.service.run(_rows(2))
    assert _statuses(report) == [QueryStatus.EXITOSA, QueryStatus.EXITOSA]
    assert report.stop_reason is None
    assert h.sleeper.sleeps == [5.0, 30.0, 5.0]


def test_circuit_events_are_logged_without_data(make: Callable[..., Harness]) -> None:
    h = make({i: PortalUnavailable for i in IDS})
    h.service.run(_rows(3))
    names = h.event_names()
    assert names.count("retry_scheduled") == 2
    assert names.count("circuit_opened") == 1
    assert names.count("batch_stopped") == 1
    text = h.log_path.read_text(encoding="utf-8")
    assert not any(i in text for i in IDS)
    assert "PERSONA FICTICIA" not in text


# --- Tiempo agotado -------------------------------------------------------------------------


def test_three_consecutive_timeouts_open_circuit(make: Callable[..., Harness]) -> None:
    h = make({i: QueryTimeout for i in IDS})
    report = h.service.run(_rows(5))
    assert _statuses(report) == [
        QueryStatus.TIEMPO_AGOTADO,
        QueryStatus.TIEMPO_AGOTADO,
        QueryStatus.TIEMPO_AGOTADO,
        PENDING,
        PENDING,
    ]
    assert report.stop_reason is StopReason.REPEATED_TIMEOUTS
    assert h.source.total_calls == 9  # 3 filas x (1 intento + 2 reintentos)
    assert "Lote detenido" in report.outcomes[3].result.observation
    assert h.event_names().count("circuit_opened") == 1


def test_two_timeouts_then_success_do_not_open_circuit(make: Callable[..., Harness]) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: QueryTimeout,
        IDS[1]: QueryTimeout,
        IDS[2]: _ok(),
        IDS[3]: QueryTimeout,
        IDS[4]: QueryTimeout,
    }
    report = make(responses).service.run(_rows(5))
    assert report.stop_reason is None
    assert _statuses(report).count(QueryStatus.TIEMPO_AGOTADO) == 4


def test_no_results_also_resets_the_timeout_streak(make: Callable[..., Harness]) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: QueryTimeout,
        IDS[1]: QueryTimeout,
        IDS[2]: _no_results(),
        IDS[3]: QueryTimeout,
    }
    report = make(responses, policy=BackoffRetryPolicy.from_settings(_Cfg(0, ()))).service.run(
        _rows(4)
    )
    assert report.stop_reason is None


def test_timeout_recovered_on_retry_counts_as_success(make: Callable[..., Harness]) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: QueryTimeout,
        IDS[1]: QueryTimeout,
        IDS[2]: [QueryTimeout, QueryTimeout, _ok()],
        IDS[3]: QueryTimeout,
    }
    report = make(responses).service.run(_rows(4))
    assert report.stop_reason is None
    assert report.outcomes[2].result.status is QueryStatus.EXITOSA


# --- Estructura cambiada e intervención humana ----------------------------------------------


def test_structure_changed_stops_batch(make: Callable[..., Harness]) -> None:
    h = make({IDS[1]: StructureChanged})
    report = h.service.run(_rows(4))
    assert _statuses(report) == [
        QueryStatus.EXITOSA,
        QueryStatus.ESTRUCTURA_CAMBIADA,
        PENDING,
        PENDING,
    ]
    assert report.stop_reason is StopReason.STRUCTURE_CHANGED
    assert h.source.total_calls == 2


def test_human_intervention_is_never_retried(make: Callable[..., Harness]) -> None:
    h = make({IDS[0]: HumanInterventionRequired}, confirmations=(True,))
    report = h.service.run(_rows(1))
    assert h.source.total_calls == 1
    assert report.outcomes[0].result.status is BLOCKED
    assert h.sleeper.sleeps == [5.0]  # solo el ritmo inicial, ningún backoff


def test_two_consecutive_blocks_stop_batch(make: Callable[..., Harness]) -> None:
    h = make({i: AccessBlocked for i in IDS}, confirmations=(True,))
    report = h.service.run(_rows(5))
    assert h.source.total_calls == 2
    assert _statuses(report) == [BLOCKED, BLOCKED, PENDING, PENDING, PENDING]
    assert report.stop_reason is StopReason.REPEATED_BLOCKS
    assert len(h.operator.confirm_prompts) == 1  # solo el 1.º bloqueo pregunta
    assert SECURITY_NOTE in report.outcomes[2].result.observation
    h.operator.assert_no_full_identification(*IDS)


def test_human_intervention_and_access_blocked_both_count_as_blocks(
    make: Callable[..., Harness],
) -> None:
    h = make({IDS[0]: HumanInterventionRequired, IDS[1]: AccessBlocked}, confirmations=(True,))
    report = h.service.run(_rows(4))
    assert h.source.total_calls == 2
    assert report.stop_reason is StopReason.REPEATED_BLOCKS


def test_success_between_blocks_resets_the_streak_and_asks_again(
    make: Callable[..., Harness],
) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: HumanInterventionRequired,
        IDS[2]: HumanInterventionRequired,
    }
    h = make(responses, confirmations=(True, True))
    report = h.service.run(_rows(4))
    assert report.stop_reason is None
    assert len(h.operator.confirm_prompts) == 2
    assert h.source.total_calls == 4


def test_operator_declines_stops_batch(make: Callable[..., Harness]) -> None:
    h = make({i: HumanInterventionRequired for i in IDS})
    report = h.service.run(_rows(3))  # sin confirmaciones: el operador declina
    assert h.source.total_calls == 1
    assert _statuses(report) == [BLOCKED, PENDING, PENDING]
    assert report.stop_reason is StopReason.OPERATOR_DECLINED
    assert SECURITY_NOTE in report.outcomes[1].result.observation


def test_operator_prompt_has_no_identification(make: Callable[..., Harness]) -> None:
    h = make({IDS[0]: AccessBlocked}, confirmations=(True,))
    h.service.run(_rows(1))
    assert len(h.operator.confirm_prompts) == 1
    assert not any(i in m for m in h.operator.all_messages for i in IDS)


# --- Ritmo (G12) ------------------------------------------------------------------------------


def test_pacing_waits_min_delay_between_paced_queries(make: Callable[..., Harness]) -> None:
    h = make({}, min_delay=5.0)
    h.service.run(_rows(3))
    assert h.sleeper.sleeps == [5.0, 5.0, 5.0]  # también antes de la primera (L-3)


def test_unpaced_source_never_sleeps(make: Callable[..., Harness]) -> None:
    h = make({}, paced=False)
    h.service.run(_rows(3))
    assert h.sleeper.sleeps == []


def test_pacing_ignores_duplicates(make: Callable[..., Harness]) -> None:
    h = make({}, min_delay=5.0)
    rows = [_rows(2)[0], InputRow(row_index=1, raw_identification=IDS[0]), _rows(2)[1]]
    h.service.run(rows)
    assert h.sleeper.sleeps == [5.0, 5.0]


# --- Fallos inesperados de política y operador -> informe parcial -------------------------------


class _RaisingPolicy:
    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        raise RuntimeError("política rota " + IDS[0])


class _RaisingOperator(OperatorDouble):
    def confirm_continue(self, message: str) -> bool:
        raise RuntimeError("operador roto " + IDS[0])


def test_policy_failure_returns_partial_report(make: Callable[..., Harness]) -> None:
    h = make({IDS[1]: PortalUnavailable}, policy=_RaisingPolicy())
    report = h.service.run(_rows(4))
    assert len(report.outcomes) == 4
    assert report.stop_reason is StopReason.UNEXPECTED_ERROR
    assert _statuses(report) == [
        QueryStatus.EXITOSA,
        QueryStatus.ESTRUCTURA_CAMBIADA,
        PENDING,
        PENDING,
    ]
    assert IDS[0] not in h.log_path.read_text(encoding="utf-8")


def test_operator_failure_counts_as_declined_and_returns_partial_report(
    logger: logging.Logger, tmp_path: Path
) -> None:
    source = FakeSource({IDS[0]: AccessBlocked}, paced=False)
    service = BatchQueryService(
        source,
        ContingencySource(),
        _RaisingOperator(),
        FixedClock.on(TODAY),
        FakeSleeper(),
        Settings(_env_file=None),
        logger,
    )
    report = service.run(_rows(3))
    assert _statuses(report) == [BLOCKED, PENDING, PENDING]
    assert report.stop_reason is StopReason.OPERATOR_DECLINED
    assert SECURITY_NOTE in report.outcomes[1].result.observation
    log_text = (tmp_path / f"run_{RUN_ID}.jsonl").read_text(encoding="utf-8")
    assert "OPERATOR_FAILED" in log_text
    assert IDS[0] not in (tmp_path / f"run_{RUN_ID}.jsonl").read_text(encoding="utf-8")


# --- Catálogo de eventos ---------------------------------------------------------------------


def test_new_event_names_belong_to_closed_catalog() -> None:
    assert {"circuit_opened", "batch_stopped", "retry_scheduled"} <= set(EVENT_NAMES)
    assert set(EVENT_NAMES) <= {event.value for event in LogEvent}


def test_policy_does_not_retry_errors_outside_the_retry_table() -> None:
    policy = BackoffRetryPolicy.from_settings(_Cfg(2, (30, 120)))
    assert policy.delay_before_retry(ExportError(), 1) is None


# --- Dedupe según quién resuelve la fila (respaldo con copia del RUT) ---------------------------

COPY = {"raw_copy_date": "2026-10-01", "raw_responsible": "USR-001"}
VALIDATED = QueryStatus.VALIDADA_COPIA_RUT


def _copy_fallback() -> DocumentCopySource:
    return DocumentCopySource(ContingencySource(), FixedClock.on(TODAY))


def _dup_rows(first_with_copy: bool) -> list[InputRow]:
    """Dos filas con la misma identificación: una con copia vigente y otra sin ella."""
    extras = [COPY, {}] if first_with_copy else [{}, COPY]
    return [
        InputRow(row_index=i, raw_identification=IDS[0], **extra) for i, extra in enumerate(extras)
    ]


@pytest.mark.parametrize("error", [PortalUnavailable, StructureChanged])
@pytest.mark.parametrize("first_with_copy", [True, False])
def test_rows_resolved_by_fallback_do_not_share_copy_evidence(
    make: Callable[..., Harness], error: Callable[[], RutCheckerError], first_with_copy: bool
) -> None:
    h = make({IDS[0]: error}, fallback=_copy_fallback())
    report = h.service.run(_dup_rows(first_with_copy))
    by_copy = [VALIDATED, PENDING] if first_with_copy else [PENDING, VALIDATED]
    expected = by_copy
    if error is StructureChanged:
        # la fila que dispara la parada conserva ESTRUCTURA_CAMBIADA; la otra va al respaldo
        expected = [QueryStatus.ESTRUCTURA_CAMBIADA, by_copy[1]]
    assert _statuses(report) == expected


def test_rows_after_circuit_resolved_by_fallback_keep_their_own_evidence(
    make: Callable[..., Harness],
) -> None:
    h = make({IDS[0]: PortalUnavailable}, fallback=_copy_fallback())
    rows = [
        InputRow(row_index=0, raw_identification=IDS[0]),
        InputRow(row_index=1, raw_identification=IDS[1]),
        InputRow(row_index=2, raw_identification=IDS[1], **COPY),
        InputRow(row_index=3, raw_identification=IDS[1]),
    ]
    report = h.service.run(rows)
    assert _statuses(report) == [PENDING, PENDING, VALIDATED, PENDING]


def test_success_before_a_stop_is_reused_after_it(make: Callable[..., Harness]) -> None:
    h = make({IDS[1]: StructureChanged})
    rows = [
        InputRow(row_index=0, raw_identification=IDS[0]),
        InputRow(row_index=1, raw_identification=IDS[1]),
        InputRow(row_index=2, raw_identification=IDS[0]),
    ]
    report = h.service.run(rows)
    assert _statuses(report)[2] is QueryStatus.EXITOSA
    assert h.source.calls_for(IDS[0]) == 1


def test_non_success_primary_result_is_not_reused_after_a_stop(
    make: Callable[..., Harness],
) -> None:
    h = make({IDS[0]: StructureChanged})
    rows = [
        InputRow(row_index=0, raw_identification=IDS[0]),
        InputRow(row_index=1, raw_identification=IDS[0]),
    ]
    report = h.service.run(rows)
    assert _statuses(report) == [QueryStatus.ESTRUCTURA_CAMBIADA, PENDING]


# --- Fallos de sesión repetidos (O-1) -----------------------------------------------------------

SESSION = QueryStatus.SESION_VENCIDA


def test_three_consecutive_session_failures_open_circuit(make: Callable[..., Harness]) -> None:
    h = make({i: SessionExpired for i in IDS})
    report = h.service.run(_rows(5))
    assert _statuses(report) == [SESSION, SESSION, SESSION, PENDING, PENDING]
    assert report.stop_reason is StopReason.REPEATED_SESSION_FAILURES
    assert h.source.total_calls == 6  # 3 filas x (1 intento + 1 reintento)
    assert "Lote detenido: fallos de sesión repetidos" in report.outcomes[3].result.observation
    assert h.event_names().count("circuit_opened") == 1


def test_session_expired_and_incomplete_result_share_the_streak(
    make: Callable[..., Harness],
) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: SessionExpired,
        IDS[1]: IncompleteResult,
        IDS[2]: SessionExpired,
    }
    report = make(responses).service.run(_rows(5))
    assert report.stop_reason is StopReason.REPEATED_SESSION_FAILURES
    assert _statuses(report)[1] is QueryStatus.RESULTADO_INCOMPLETO


def test_success_resets_the_session_streak(make: Callable[..., Harness]) -> None:
    responses: dict[str, Programmed] = {
        IDS[0]: SessionExpired,
        IDS[1]: IncompleteResult,
        IDS[3]: SessionExpired,
        IDS[4]: IncompleteResult,
    }
    report = make(responses).service.run(_rows(5))
    assert report.stop_reason is None
