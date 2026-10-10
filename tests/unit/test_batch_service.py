"""Pruebas del núcleo de `BatchQueryService` (T-35)."""

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest
from doubles import FakeSleeper, FixedClock, OperatorDouble

from rut_checker.adapters.contingency_source import ContingencySource
from rut_checker.adapters.document_copy_source import DocumentCopySource
from rut_checker.adapters.fake_source import FakeSource
from rut_checker.application.batch_service import BatchQueryService
from rut_checker.application.report import BatchReport, StopReason
from rut_checker.application.retry_policy import MAX_ATTEMPTS, NoRetry, RetryPolicy
from rut_checker.application.run_log import EVENT_NAMES
from rut_checker.application.translation import translate
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
from rut_checker.domain.models import IdentificationInput, InputRow, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.infra.logging import LogEvent, close_logging, configure_logging
from rut_checker.infra.settings import Settings
from rut_checker.ports.rut_source import RutSourcePort

ID_1 = "1000000001"
ID_2 = "1000000002"
ID_3 = "1000000003"
NIT_BASE = "900000001"
RUN_ID = "20261009-120000-abcd"
TODAY = date(2026, 10, 9)
STOP_NOTE = "Lote detenido"
_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def _reference_dv(number: str) -> str:
    total = sum(int(d) * w for d, w in zip(reversed(number), _WEIGHTS, strict=False)) % 11
    return str(total if total in (0, 1) else 11 - total)


@dataclass
class Harness:
    """Servicio armado con dobles y acceso a lo que registran."""

    service: BatchQueryService
    primary: RutSourcePort
    fallback: RutSourcePort
    operator: OperatorDouble
    sleeper: FakeSleeper
    log_path: Path

    @property
    def fake(self) -> FakeSource:
        """La fuente primaria cuando es un `FakeSource` (para contar llamadas)."""
        assert isinstance(self.primary, FakeSource)
        return self.primary

    def log_text(self) -> str:
        return self.log_path.read_text(encoding="utf-8")

    def log_events(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.log_text().splitlines()]


class _Source:
    """Fuente de prueba que lanza lo que se le pida (excepciones que no son de dominio)."""

    paced = False

    def __init__(self, error: Callable[[], BaseException], kind: SourceKind = SourceKind.FAKE):
        self._error = error
        self._kind = kind
        self.calls = 0
        self.close_count = 0

    @property
    def kind(self) -> SourceKind:
        return self._kind

    def query(self, ident: IdentificationInput) -> RutResult:
        self.calls += 1
        raise self._error()

    def close(self) -> None:
        self.close_count += 1


class _CloseFails(ContingencySource):
    def close(self) -> None:
        raise OSError("falla al cerrar " + ID_1)


@pytest.fixture
def logger(tmp_path: Path) -> Iterator[logging.Logger]:
    run_logger = configure_logging(RUN_ID, tmp_path)
    yield run_logger
    close_logging(run_logger)


@pytest.fixture
def make(logger: logging.Logger, tmp_path: Path) -> Callable[..., Harness]:
    def factory(
        primary: RutSourcePort | None = None,
        fallback: RutSourcePort | None = None,
        *,
        policy: RetryPolicy | None = None,
        min_delay: float = 5.0,
    ) -> Harness:
        used_primary = primary if primary is not None else FakeSource()
        used_fallback = fallback if fallback is not None else ContingencySource()
        operator = OperatorDouble()
        sleeper = FakeSleeper()
        settings = Settings(_env_file=None, min_delay_between_queries_s=min_delay)
        service = BatchQueryService(
            used_primary,
            used_fallback,
            operator,
            FixedClock.on(TODAY),
            sleeper,
            settings,
            logger,
            retry_policy=policy or NoRetry(),
        )
        log_path = tmp_path / f"run_{RUN_ID}.jsonl"
        return Harness(service, used_primary, used_fallback, operator, sleeper, log_path)

    return factory


def _row(index: int, raw: str | int | float | None, **raw_fields: str) -> InputRow:
    return InputRow(row_index=index, raw_identification=raw, **raw_fields)


def _ok(estado: str = "ACTIVO") -> RutResult:
    return RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.FAKE,
        estado_rut=estado,
        name="PERSONA FICTICIA UNO",
    )


def _statuses(report: BatchReport) -> list[QueryStatus]:
    return [outcome.result.status for outcome in report.outcomes]


# --- Validación y entrada inválida -------------------------------------------------------


def test_invalid_input_never_calls_source(make: Callable[..., Harness]) -> None:
    h = make()
    rows = [_row(0, "12A45"), _row(1, ""), _row(2, None), _row(3, NIT_BASE, raw_dv="0")]
    # el DV "0" es incorrecto salvo que coincida por casualidad con el calculado
    assert _reference_dv(NIT_BASE) != "0"
    report = h.service.run(rows)
    assert h.fake.total_calls == 0
    assert _statuses(report) == [QueryStatus.ENTRADA_INVALIDA] * 4
    for outcome in report.outcomes:
        assert outcome.identification is None
        assert outcome.result.source is SourceKind.SIN_CONSULTA
        assert outcome.result.observation.startswith("Número inválido: ")
    assert "12A45" not in "".join(o.result.observation for o in report.outcomes)


def test_invalid_row_with_unreadable_copy_date_is_invalid(make: Callable[..., Harness]) -> None:
    h = make()
    report = h.service.run(
        [
            _row(0, ID_1, raw_copy_date="mañana", raw_responsible="USR-001"),
            _row(1, ID_2, raw_copy_date="2026-10-01"),
            _row(2, ID_3, raw_note="x" * 201),
        ]
    )
    assert _statuses(report) == [QueryStatus.ENTRADA_INVALIDA] * 3
    assert h.fake.total_calls == 0
    reasons = [o.result.observation for o in report.outcomes]
    assert InvalidReason.UNREADABLE_COPY_DATE.value in reasons[0]
    assert InvalidReason.INVALID_RESPONSIBLE.value in reasons[1]
    assert InvalidReason.OBSERVATION_TOO_LONG.value in reasons[2]


def test_valid_with_result_is_exitosa(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: _ok("ACTIVO")}))
    report = h.service.run([_row(0, ID_1, raw_note="nota del área")])
    outcome = report.outcomes[0]
    assert outcome.result.status is QueryStatus.EXITOSA
    assert outcome.result.estado_rut == "ACTIVO"
    assert outcome.identification is not None
    assert outcome.identification.identification == ID_1
    assert outcome.identification.note == "nota del área"
    assert outcome.queried_at.utcoffset() == timedelta(hours=-5)
    assert outcome.duration_ms == 0


# --- Dedupe ------------------------------------------------------------------------------


def test_duplicates_query_once_and_share_result(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: _ok("ACTIVO")}))
    rows = [_row(0, ID_1), _row(1, ID_2), _row(2, " 1.000.000.001 "), _row(3, float(ID_1))]
    report = h.service.run(rows)
    assert h.fake.calls_for(ID_1) == 1
    assert h.fake.calls_for(ID_2) == 1
    first, _, dup_a, dup_b = report.outcomes
    assert first.result == dup_a.result == dup_b.result
    assert [o.row.row_index for o in report.outcomes] == [0, 1, 2, 3]
    assert dup_a.duration_ms == 0


# --- Lotes mixtos y un estado por fila ----------------------------------------------------


def test_mixed_batch(make: Callable[..., Harness]) -> None:
    wrong_dv = str((int(_reference_dv(NIT_BASE)) + 1) % 10)
    glued = NIT_BASE + _reference_dv(NIT_BASE)
    h = make(FakeSource({ID_2: lambda: QueryTimeout()}))
    report = h.service.run(
        [
            _row(0, ID_1),
            _row(1, NIT_BASE, raw_dv=wrong_dv),
            _row(2, ID_1),
            _row(3, ID_2),
            _row(4, glued),
        ]
    )
    assert _statuses(report) == [
        QueryStatus.EXITOSA,
        QueryStatus.ENTRADA_INVALIDA,
        QueryStatus.EXITOSA,
        QueryStatus.TIEMPO_AGOTADO,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
    ]
    assert h.fake.total_calls == 2
    assert report.counts == {
        QueryStatus.EXITOSA: 2,
        QueryStatus.ENTRADA_INVALIDA: 1,
        QueryStatus.TIEMPO_AGOTADO: 1,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL: 1,
    }
    assert report.stop_reason is None
    assert not report.stopped


def test_each_row_gets_exactly_one_status(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_2: lambda: PortalUnavailable()}))
    rows = [_row(i, raw) for i, raw in enumerate([ID_1, ID_2, "x", ID_1, None, ID_3])]
    report = h.service.run(rows)
    assert [o.row for o in report.outcomes] == rows
    assert sum(report.counts.values()) == len(rows)
    assert len(report.outcomes) == len(rows)


def test_empty_batch_returns_empty_report(make: Callable[..., Harness]) -> None:
    h = make()
    report = h.service.run([])
    assert report.outcomes == ()
    assert report.counts == {}


# --- Posible NIT con DV pegado -------------------------------------------------------------


def test_possible_glued_check_digit_goes_to_pending_without_query(
    make: Callable[..., Harness],
) -> None:
    glued = NIT_BASE + _reference_dv(NIT_BASE)
    h = make()
    report = h.service.run([_row(0, glued)])
    outcome = report.outcomes[0]
    assert outcome.result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert outcome.result.source is SourceKind.CONTINGENCIA_MANUAL
    assert "posible NIT con DV pegado" in outcome.result.observation
    assert outcome.identification is not None
    assert h.fake.total_calls == 0


def test_glued_check_digit_with_valid_copy_still_goes_to_pending(
    make: Callable[..., Harness],
) -> None:
    glued = NIT_BASE + _reference_dv(NIT_BASE)
    h = make()
    report = h.service.run([_row(0, glued, raw_copy_date="2026-10-01", raw_responsible="USR-001")])
    assert report.outcomes[0].result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert h.fake.total_calls == 0


# --- Fuente de la columna `fuente` ---------------------------------------------------------


def test_fuente_column_comes_from_result_source(make: Callable[..., Harness]) -> None:
    clock = FixedClock.on(TODAY)
    copy_source = DocumentCopySource(ContingencySource(), clock)
    h = make(copy_source)
    report = h.service.run(
        [
            _row(0, ID_1, raw_copy_date="2026-08-01", raw_responsible="USR-001"),
            _row(1, ID_2, raw_copy_date="2026-10-01", raw_responsible="USR-001"),
            _row(2, ID_3),
        ]
    )
    expired, valid, none = report.outcomes
    assert copy_source.kind is SourceKind.COPIA_RUT_TERCERO
    assert expired.result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert expired.result.source is SourceKind.CONTINGENCIA_MANUAL
    assert valid.result.status is QueryStatus.VALIDADA_COPIA_RUT
    assert valid.result.source is SourceKind.COPIA_RUT_TERCERO
    assert none.result.source is SourceKind.CONTINGENCIA_MANUAL


# --- Traducción excepción -> QueryStatus ---------------------------------------------------

_TRANSLATIONS: list[tuple[Callable[[], RutCheckerError], QueryStatus, StopReason | None]] = [
    (PortalUnavailable, QueryStatus.PORTAL_NO_DISPONIBLE, None),
    (QueryTimeout, QueryStatus.TIEMPO_AGOTADO, None),
    (SessionExpired, QueryStatus.SESION_VENCIDA, None),
    (IncompleteResult, QueryStatus.RESULTADO_INCOMPLETO, None),
    (HumanInterventionRequired, QueryStatus.REQUIERE_INTERVENCION_HUMANA, None),
    (AccessBlocked, QueryStatus.REQUIERE_INTERVENCION_HUMANA, None),
    (StructureChanged, QueryStatus.ESTRUCTURA_CAMBIADA, StopReason.STRUCTURE_CHANGED),
    (ExportError, QueryStatus.ESTRUCTURA_CAMBIADA, StopReason.UNEXPECTED_ERROR),
]


@pytest.mark.parametrize(("factory", "status", "stop"), _TRANSLATIONS)
def test_domain_exception_translation(
    make: Callable[..., Harness],
    factory: Callable[[], RutCheckerError],
    status: QueryStatus,
    stop: StopReason | None,
) -> None:
    h = make(FakeSource({ID_1: factory}))
    report = h.service.run([_row(0, ID_1)])
    outcome = report.outcomes[0]
    assert outcome.result.status is status
    assert outcome.result.source is SourceKind.FAKE  # canal intentado (primary.kind)
    assert outcome.result.estado_rut == ""
    assert outcome.result.observation
    assert report.stop_reason is stop


def test_invalid_identification_from_source_is_entrada_invalida(
    make: Callable[..., Harness],
) -> None:
    h = make(FakeSource({ID_1: lambda: InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)}))
    outcome = h.service.run([_row(0, ID_1)]).outcomes[0]
    assert outcome.result.status is QueryStatus.ENTRADA_INVALIDA
    assert outcome.result.source is SourceKind.SIN_CONSULTA
    assert outcome.identification is not None


# --- Excepción inesperada: parada segura ---------------------------------------------------


def test_unexpected_exception_stops_batch_and_logs_only_class(
    make: Callable[..., Harness],
) -> None:
    boom = _Source(lambda: RuntimeError(f"secreto {ID_1} PERSONA FICTICIA UNO"))
    h = make(boom)
    report = h.service.run(
        [_row(0, ID_2), _row(1, ID_1), _row(2, ID_3), _row(3, ID_2), _row(4, "12A45")]
    )
    assert boom.calls == 1  # solo la primera consulta llega a la fuente
    assert _statuses(report) == [
        QueryStatus.ESTRUCTURA_CAMBIADA,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        QueryStatus.ESTRUCTURA_CAMBIADA,  # duplicado de la fila 0: mismo resultado
        QueryStatus.ENTRADA_INVALIDA,
    ]
    assert report.stop_reason is StopReason.UNEXPECTED_ERROR
    assert STOP_NOTE in report.outcomes[1].result.observation
    assert report.outcomes[1].result.source is SourceKind.CONTINGENCIA_MANUAL
    text = h.log_text()
    assert "RuntimeError" in text
    assert "UNEXPECTED" in text
    for forbidden in ("secreto", "PERSONA", ID_1, ID_2):
        assert forbidden not in text


def test_keyboard_interrupt_propagates_and_sources_are_closed(
    make: Callable[..., Harness],
) -> None:
    interrupted = _Source(KeyboardInterrupt)
    fallback = FakeSource()
    h = make(interrupted, fallback)
    with pytest.raises(KeyboardInterrupt):
        h.service.run([_row(0, ID_1)])
    assert interrupted.close_count == 1
    assert fallback.close_count == 1


def test_structure_changed_sends_remaining_rows_to_fallback(make: Callable[..., Harness]) -> None:
    fallback = FakeSource(default=_pending())
    h = make(FakeSource({ID_2: StructureChanged}), fallback)
    report = h.service.run(
        [_row(0, ID_1), _row(1, ID_2), _row(2, ID_3), _row(3, ID_3), _row(4, "x")]
    )
    assert _statuses(report) == [
        QueryStatus.EXITOSA,
        QueryStatus.ESTRUCTURA_CAMBIADA,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        QueryStatus.ENTRADA_INVALIDA,
    ]
    assert report.stop_reason is StopReason.STRUCTURE_CHANGED
    assert STOP_NOTE in report.outcomes[2].result.observation
    assert fallback.total_calls == 1  # el duplicado reutiliza el resultado
    assert h.fake.total_calls == 2


def _pending() -> RutResult:
    return RutResult(
        status=QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        source=SourceKind.CONTINGENCIA_MANUAL,
        observation="Pendiente de validación manual",
    )


@pytest.mark.parametrize(
    "error", [lambda: RuntimeError("detalle " + ID_3), PortalUnavailable], ids=["raw", "domain"]
)
def test_failing_fallback_still_gives_one_status_per_row(
    make: Callable[..., Harness], error: Callable[[], Exception]
) -> None:
    h = make(
        FakeSource({ID_1: StructureChanged}),
        _Source(error),
    )
    report = h.service.run([_row(0, ID_1), _row(1, ID_3)])
    assert _statuses(report) == [
        QueryStatus.ESTRUCTURA_CAMBIADA,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
    ]
    assert report.outcomes[1].result.source is SourceKind.CONTINGENCIA_MANUAL
    assert ID_3 not in h.log_text()
    assert "detalle" not in h.log_text()


# --- Cierre de fuentes ---------------------------------------------------------------------


def test_sources_are_closed_once_at_the_end(make: Callable[..., Harness]) -> None:
    primary = FakeSource()
    fallback = FakeSource()
    h = make(primary, fallback)
    h.service.run([_row(0, ID_1)])
    assert primary.close_count == 1
    assert fallback.close_count == 1


def test_close_failure_is_logged_without_text_and_does_not_break_run(
    make: Callable[..., Harness],
) -> None:
    h = make(FakeSource(), _CloseFails())
    report = h.service.run([_row(0, ID_1)])
    assert _statuses(report) == [QueryStatus.EXITOSA]
    text = h.log_text()
    assert "OSError" in text
    assert "falla al cerrar" not in text
    assert ID_1 not in text


# --- Política de reintentos (punto de extensión de T-45) ------------------------------------


class _RetryTwice:
    """Reintenta `PortalUnavailable` hasta 2 veces con espera de 30 s."""

    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        return 30.0 if isinstance(error, PortalUnavailable) and attempt <= 2 else None


def test_default_policy_does_not_retry(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: PortalUnavailable}, paced=True))
    report = h.service.run([_row(0, ID_1)])
    assert report.outcomes[0].result.status is QueryStatus.PORTAL_NO_DISPONIBLE
    assert h.fake.total_calls == 1
    assert h.sleeper.sleeps == []


def test_injected_policy_retries_with_effective_pause_and_logs_attempt(
    make: Callable[..., Harness],
) -> None:
    source = FakeSource({ID_1: [PortalUnavailable, PortalUnavailable, _ok()]}, paced=True)
    h = make(source, policy=_RetryTwice())
    report = h.service.run([_row(0, ID_1)])
    assert report.outcomes[0].result.status is QueryStatus.EXITOSA
    assert source.total_calls == 3
    assert h.sleeper.sleeps == [30.0, 30.0]  # max(min_delay, backoff)
    events = h.log_events()
    assert [e["event"] for e in events].count("retry_scheduled") == 2
    finished = next(e for e in events if e["event"] == "row_finished")
    assert finished["attempt"] == 3


def test_retry_policy_giving_up_translates_last_error(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: PortalUnavailable}), policy=_RetryTwice())
    report = h.service.run([_row(0, ID_1)])
    assert report.outcomes[0].result.status is QueryStatus.PORTAL_NO_DISPONIBLE
    assert h.fake.total_calls == 3


# --- Ritmo mínimo seguro --------------------------------------------------------------------


def test_paced_source_waits_min_delay_between_distinct_queries(
    make: Callable[..., Harness],
) -> None:
    h = make(FakeSource(paced=True), min_delay=7.0)
    h.service.run([_row(0, ID_1), _row(1, ID_2), _row(2, ID_1), _row(3, ID_3)])
    assert h.sleeper.sleeps == [7.0, 7.0]  # sin pausa antes de la primera ni por duplicados


def test_unpaced_source_never_sleeps(make: Callable[..., Harness]) -> None:
    h = make(FakeSource(paced=False))
    h.service.run([_row(0, ID_1), _row(1, ID_2)])
    assert h.sleeper.sleeps == []


# --- Registro técnico sin datos personales --------------------------------------------------


def test_log_has_masked_ids_counts_and_no_personal_data(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: _ok("ACTIVO")}))
    h.service.run([_row(0, ID_1, raw_note="nota privada", **_COPY), _row(1, "12A45")])
    text = h.log_text()
    for forbidden in (ID_1, "PERSONA", "ACTIVO", "nota privada", "USR-001", "12A45"):
        assert forbidden not in text
    events = h.log_events()
    names = [e["event"] for e in events]
    assert names[0] == "run_started"
    assert names[-1] == "run_finished"
    assert names.count("row_finished") == 2
    finished = [e for e in events if e["event"] == "row_finished"]
    assert finished[0]["id_masked"] == "******0001"
    assert finished[0]["status"] == "EXITOSA"
    assert finished[0]["source"] == "FAKE"
    assert finished[0]["row_index"] == 0
    assert events[-1]["counts"] == {"EXITOSA": 1, "ENTRADA_INVALIDA": 1}


def test_batch_stopped_event_is_logged(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: StructureChanged}))
    h.service.run([_row(0, ID_1)])
    stopped = [e for e in h.log_events() if e["event"] == "batch_stopped"]
    assert len(stopped) == 1
    assert stopped[0]["error_code"] == "STRUCTURE_CHANGED"
    assert stopped[0]["row_index"] == 0


def test_run_log_event_names_belong_to_closed_catalog() -> None:
    assert {LogEvent(name) for name in EVENT_NAMES} <= set(LogEvent)
    assert LogEvent.UNLISTED.value not in EVENT_NAMES


def test_validated_copy_rows_after_a_stop_keep_their_status(make: Callable[..., Harness]) -> None:
    fallback = DocumentCopySource(ContingencySource(), FixedClock.on(TODAY))
    h = make(FakeSource({ID_1: StructureChanged}), fallback)
    report = h.service.run(
        [
            _row(0, ID_1),
            _row(1, ID_2, raw_copy_date="2026-10-01", raw_responsible="USR-001"),
            _row(2, ID_3),
        ]
    )
    assert _statuses(report)[1:] == [
        QueryStatus.VALIDADA_COPIA_RUT,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
    ]
    assert STOP_NOTE not in report.outcomes[1].result.observation
    assert STOP_NOTE in report.outcomes[2].result.observation


def test_float_identification_is_masked_in_the_log(make: Callable[..., Harness]) -> None:
    h = make()
    h.service.run([_row(0, 12345678.5), _row(1, 12.0)])
    assert ID_1 not in h.log_text()


# --- Dedupe con evidencia y nota (decisión A) ------------------------------------------------

_COPY = {"raw_copy_date": "2026-10-01", "raw_responsible": "USR-001"}


def test_duplicates_with_different_copy_evidence_are_not_shared(
    make: Callable[..., Harness],
) -> None:
    primary = DocumentCopySource(ContingencySource(), FixedClock.on(TODAY))
    h = make(primary)
    without_first = h.service.run([_row(0, ID_1), _row(1, ID_1, **_COPY)])
    assert _statuses(without_first) == [
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        QueryStatus.VALIDADA_COPIA_RUT,
    ]
    h2 = make(DocumentCopySource(ContingencySource(), FixedClock.on(TODAY)))
    with_first = h2.service.run([_row(0, ID_1, **_COPY), _row(1, ID_1)])
    assert _statuses(with_first) == [
        QueryStatus.VALIDADA_COPIA_RUT,
        QueryStatus.PENDIENTE_VALIDACION_MANUAL,
    ]


def test_duplicates_with_different_notes_keep_their_own_note(
    make: Callable[..., Harness],
) -> None:
    h = make(FakeSource())
    report = h.service.run([_row(0, ID_1, raw_note="a"), _row(1, ID_1, raw_note="b")])
    assert h.fake.calls_for(ID_1) == 2
    notes = [o.identification.note for o in report.outcomes if o.identification]
    assert notes == ["a", "b"]


def test_duplicates_with_same_evidence_and_note_share_result(
    make: Callable[..., Harness],
) -> None:
    h = make(FakeSource())
    h.service.run([_row(0, ID_1, raw_note="a", **_COPY), _row(1, ID_1, raw_note="a", **_COPY)])
    assert h.fake.calls_for(ID_1) == 1


def test_responsible_without_copy_date_is_invalid(make: Callable[..., Harness]) -> None:
    h = make()
    report = h.service.run([_row(0, ID_1, raw_responsible="USR-001")])
    outcome = report.outcomes[0]
    assert outcome.result.status is QueryStatus.ENTRADA_INVALIDA
    assert InvalidReason.RESPONSIBLE_WITHOUT_COPY_DATE.value in outcome.result.observation
    assert not any(c.isdigit() for c in InvalidReason.RESPONSIBLE_WITHOUT_COPY_DATE.value)
    assert h.fake.total_calls == 0


# --- Reintentos acotados y política hostil (M-1) -----------------------------------------------


class _Hostile:
    def __init__(self, delay: float) -> None:
        self._delay = delay

    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        return self._delay


def test_human_intervention_is_never_retried(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: HumanInterventionRequired}, paced=True), policy=_Hostile(1.0))
    report = h.service.run([_row(0, ID_1)])
    assert h.fake.total_calls == 1
    assert report.outcomes[0].result.status is QueryStatus.REQUIERE_INTERVENCION_HUMANA


@pytest.mark.parametrize(
    "factory",
    [
        HumanInterventionRequired,
        AccessBlocked,
        StructureChanged,
        IncompleteResult,
        lambda: InvalidIdentification(InvalidReason.EMPTY),
    ],
)
def test_never_retried_errors_ignore_hostile_policy(
    make: Callable[..., Harness], factory: Callable[[], RutCheckerError]
) -> None:
    h = make(FakeSource({ID_1: factory}), policy=_Hostile(1.0))
    h.service.run([_row(0, ID_1)])
    assert h.fake.total_calls == 1
    assert h.sleeper.sleeps == []


def test_retries_are_bounded_even_with_hostile_policy(make: Callable[..., Harness]) -> None:
    h = make(FakeSource({ID_1: PortalUnavailable}), policy=_Hostile(1.0))
    report = h.service.run([_row(0, ID_1)])
    assert h.fake.total_calls == MAX_ATTEMPTS
    assert report.outcomes[0].result.status is QueryStatus.PORTAL_NO_DISPONIBLE


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), -1.0])
def test_non_finite_or_negative_delay_means_no_retry(
    make: Callable[..., Harness], delay: float
) -> None:
    h = make(FakeSource({ID_1: PortalUnavailable}), policy=_Hostile(delay))
    h.service.run([_row(0, ID_1)])
    assert h.fake.total_calls == 1
    assert h.sleeper.sleeps == []


def test_pause_is_max_of_min_delay_and_backoff(make: Callable[..., Harness]) -> None:
    source = FakeSource({ID_1: [PortalUnavailable, _ok()]}, paced=True)
    h = make(source, policy=_Hostile(2.0), min_delay=7.0)
    h.service.run([_row(0, ID_1)])
    assert h.sleeper.sleeps == [7.0]


# --- Respaldo, un solo uso, enmascarado ---------------------------------------------------------


def test_paced_fallback_is_rejected(make: Callable[..., Harness]) -> None:
    with pytest.raises(ValueError, match="respaldo"):
        make(fallback=FakeSource(paced=True))


def test_portal_fallback_is_rejected(make: Callable[..., Harness]) -> None:
    with pytest.raises(ValueError, match="respaldo"):
        make(fallback=_Source(RuntimeError, SourceKind.PORTAL_DIAN_C1))


def test_run_is_single_use(make: Callable[..., Harness]) -> None:
    h = make()
    h.service.run([_row(0, ID_1)])
    with pytest.raises(RuntimeError, match="un solo uso"):
        h.service.run([_row(0, ID_1)])


def test_masked_id_of_invalid_rows(make: Callable[..., Harness]) -> None:
    h = make()
    h.service.run([_row(0, 12345678.5), _row(1, 12.0), _row(2, "12A45"), _row(3, None)])
    finished = [e for e in h.log_events() if e["event"] == "row_finished"]
    assert [e.get("id_masked") for e in finished] == ["*", "**", "*", None]


def test_failed_fallback_of_copy_source_uses_manual_contingency_source(
    make: Callable[..., Harness],
) -> None:
    primary = DocumentCopySource(FakeSource({ID_1: PortalUnavailable}), FixedClock.on(TODAY))
    h = make(primary)
    outcome = h.service.run([_row(0, ID_1)]).outcomes[0]
    assert outcome.result.status is QueryStatus.PORTAL_NO_DISPONIBLE
    assert outcome.result.source is SourceKind.CONTINGENCIA_MANUAL


def test_translate_is_the_single_mapping() -> None:
    assert translate(StructureChanged()).stop is StopReason.STRUCTURE_CHANGED
    assert translate(ExportError()).unexpected


def test_paced_duplicates_with_different_notes_query_once(make: Callable[..., Harness]) -> None:
    h = make(FakeSource(paced=True))
    report = h.service.run(
        [
            _row(0, ID_1, raw_note="a"),
            _row(1, ID_1, raw_note="b", **_COPY),
            _row(2, ID_1),
        ]
    )
    assert h.fake.calls_for(ID_1) == 1
    assert h.sleeper.sleeps == []
    notes = [o.identification.note for o in report.outcomes if o.identification]
    assert notes == ["a", "b", None]


def test_note_whitespace_does_not_split_duplicates(make: Callable[..., Harness]) -> None:
    h = make(FakeSource())
    h.service.run([_row(0, ID_1, raw_note=" nota  x "), _row(1, ID_1, raw_note="nota x")])
    assert h.fake.calls_for(ID_1) == 1
