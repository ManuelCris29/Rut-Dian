"""Pruebas de `ContingencySource` y `DocumentCopySource` (T-39; G9, G10, D-3)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from doubles import BOGOTA, FixedClock, assert_clock_contract

from rut_checker.adapters.contingency_source import ContingencySource
from rut_checker.adapters.document_copy_source import DocumentCopySource
from rut_checker.adapters.fake_source import FakeSource
from rut_checker.domain.models import (
    MAX_NOTE_LENGTH,
    CopyEvidence,
    IdentificationInput,
    RutResult,
)
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.ports.clock import Clock
from rut_checker.ports.rut_source import RutSourcePort

MAX_OBSERVATION = MAX_NOTE_LENGTH + 130  # parte fija (~75-120) + prefijo de nota
ID_1 = "1000000001"
TODAY = date(2026, 10, 9)


def _ident(
    days_ago: int | None = None,
    *,
    note: str | None = None,
    responsible: str = "USR-001",
) -> IdentificationInput:
    evidence = (
        None
        if days_ago is None
        else CopyEvidence(copy_date=TODAY - timedelta(days=days_ago), responsible=responsible)
    )
    return IdentificationInput(identification=ID_1, copy_evidence=evidence, note=note)


def _source() -> DocumentCopySource:
    return DocumentCopySource(ContingencySource(), FixedClock.on(TODAY))


def test_sources_satisfy_the_port_and_are_not_paced() -> None:
    for source in (ContingencySource(), _source()):
        assert isinstance(source, RutSourcePort)
        assert source.paced is False
    assert isinstance(FixedClock.on(TODAY), Clock)
    assert ContingencySource().kind is SourceKind.CONTINGENCIA_MANUAL
    assert _source().kind is SourceKind.COPIA_RUT_TERCERO


def test_contingency_is_always_pending_manual() -> None:
    result = ContingencySource().query(_ident())
    assert result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert result.source is SourceKind.CONTINGENCIA_MANUAL
    assert result.observation == "Pendiente de validación manual"
    assert result.estado_rut == result.name == ""


def test_without_evidence_delegates_to_contingency() -> None:
    sentinel = RutResult(
        status=QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        source=SourceKind.CONTINGENCIA_MANUAL,
        observation="del fallback",
    )
    fallback = FakeSource(default=sentinel)
    result = DocumentCopySource(fallback, FixedClock.on(TODAY)).query(_ident())
    assert result == sentinel
    assert fallback.total_calls == 1


def test_valid_copy_is_validada_copia_rut_with_date_and_code() -> None:
    result = _source().query(_ident(30))
    assert result.status is QueryStatus.VALIDADA_COPIA_RUT
    assert result.source is SourceKind.COPIA_RUT_TERCERO
    assert result.observation == (
        "Validado contra copia del RUT de fecha 2026-09-09; responsable: USR-001"
    )


def test_estado_rut_and_name_stay_empty() -> None:
    result = _source().query(_ident(0))
    assert result.estado_rut == ""
    assert result.name == ""


def test_valid_copy_appends_area_note() -> None:
    result = _source().query(_ident(5, note="Contrato 45"))
    assert result.observation.endswith("responsable: USR-001. Observación del área: Contrato 45")


def test_area_note_is_masked_and_bounded() -> None:
    result = _source().query(_ident(5, note="NIT 1000000001 " + "x" * 185))
    assert ID_1 not in result.observation
    assert "******0001" in result.observation
    assert len(result.observation) <= MAX_OBSERVATION


def test_area_note_whitespace_is_collapsed_before_masking() -> None:
    result = _source().query(_ident(5, note="NIT 1000000\n001\t ok"))
    assert "\n" not in result.observation
    assert "\t" not in result.observation
    assert "******0001 ok" in result.observation


@pytest.mark.parametrize("days_ago", [31, -1])
def test_pending_copy_keeps_masked_area_note(days_ago: int) -> None:
    result = _source().query(_ident(days_ago, note="Ver 1000000001"))
    assert result.observation.endswith("Observación del área: Ver ******0001")


def test_real_composition_without_evidence_is_contingency() -> None:
    source = DocumentCopySource(ContingencySource(), FixedClock.on(TODAY))
    result = source.query(_ident())
    assert result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert result.source is SourceKind.CONTINGENCIA_MANUAL
    assert result.observation == "Pendiente de validación manual"


def test_paced_follows_fallback() -> None:
    clock = FixedClock.on(TODAY)
    assert DocumentCopySource(FakeSource(paced=True), clock).paced is True
    assert DocumentCopySource(FakeSource(paced=False), clock).paced is False


def test_fixed_clock_satisfies_contract() -> None:
    assert_clock_contract(FixedClock.on(TODAY))
    late_utc = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)  # 22:00 del 9 en Bogotá
    clock = FixedClock(late_utc)
    assert_clock_contract(clock)
    assert clock.today() == date(2026, 10, 9)
    assert clock.now().astimezone(BOGOTA).hour == 22


def test_blank_note_is_omitted() -> None:
    result = _source().query(_ident(5, note="   "))
    assert "Observación del área" not in result.observation


def test_expired_copy_is_pending_with_copia_vencida() -> None:
    result = _source().query(_ident(31))
    assert result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert result.source is SourceKind.CONTINGENCIA_MANUAL
    assert "copia vencida (2026-09-08)" in result.observation
    assert result.estado_rut == result.name == ""


def test_future_copy_is_pending_with_invalid_date() -> None:
    result = _source().query(_ident(-1))
    assert result.status is QueryStatus.PENDIENTE_VALIDACION_MANUAL
    assert result.source is SourceKind.CONTINGENCIA_MANUAL
    assert "fecha de copia inválida" in result.observation


@pytest.mark.parametrize("days_ago", [31, -1])
def test_pending_copy_does_not_call_fallback_nor_leak_id(days_ago: int) -> None:
    fallback = FakeSource()
    result = DocumentCopySource(fallback, FixedClock.on(TODAY)).query(_ident(days_ago))
    assert fallback.total_calls == 0
    assert ID_1 not in result.observation


def test_close_is_idempotent_and_closes_fallback() -> None:
    fallback = FakeSource()
    source = DocumentCopySource(fallback, FixedClock.on(TODAY))
    source.close()
    source.close()
    ContingencySource().close()
    assert fallback.close_count == 2
