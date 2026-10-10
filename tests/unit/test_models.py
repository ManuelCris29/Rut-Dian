"""Pruebas de los modelos de dominio (entrada, evidencia, resultado, desenlace)."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from rut_checker.domain.errors import IncompleteResult, InvalidIdentification, InvalidReason
from rut_checker.domain.models import (
    CopyEvidence,
    IdentificationInput,
    InputRow,
    QueryOutcome,
    RutResult,
)
from rut_checker.domain.status import QueryStatus, SourceKind

ID = "1000000001"
NAME = "PERSONA FICTICIA UNO"
COPY_DATE = date(2026, 9, 9)


def _evidence(responsible: str = "USR-001") -> CopyEvidence:
    return CopyEvidence(copy_date=COPY_DATE, responsible=responsible)


def _validada(**overrides: str) -> RutResult:
    return RutResult(
        status=QueryStatus.VALIDADA_COPIA_RUT, source=SourceKind.COPIA_RUT_TERCERO, **overrides
    )


# --- IdentificationInput -------------------------------------------------------------------


def test_identification_input_defaults() -> None:
    ident = IdentificationInput(identification=ID)
    assert ident.identification == ID
    assert ident.dv is None
    assert ident.copy_evidence is None
    assert ident.note is None


def test_models_are_frozen() -> None:
    ident = IdentificationInput(identification=ID)
    with pytest.raises(ValidationError):
        ident.identification = "1000000002"  # type: ignore[misc]  # prueba de inmutabilidad


@pytest.mark.parametrize("raw", ["12A45", "1000 0001"])
def test_identification_must_be_normalized_digits(raw: str) -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput(identification=raw)
    assert info.value.reason is InvalidReason.NON_NUMERIC
    assert raw not in str(info.value)


def test_empty_identification_is_rejected() -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput(identification="")
    assert info.value.reason is InvalidReason.EMPTY


@pytest.mark.parametrize("value", [1000000001, 1000000001.0, None, b"1000000001"])
def test_non_str_identification_is_non_numeric(value: object) -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput.model_validate({"identification": value})
    assert info.value.reason is InvalidReason.NON_NUMERIC


@pytest.mark.parametrize("dv", ["", "12", "A", 7, 0])
def test_dv_must_be_single_digit(dv: object) -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput.model_validate({"identification": ID, "dv": dv})
    assert info.value.reason is InvalidReason.BAD_CHECK_DIGIT


def test_repr_masks_identification() -> None:
    ident = IdentificationInput(
        identification=ID, dv="7", copy_evidence=_evidence(), note="nota privada del area"
    )
    for text in (repr(ident), str(ident), f"{ident}", f"{ident!r}"):
        assert ID not in text
        assert "******0001" in text
        assert "USR-001" not in text
        assert "nota privada" not in text


def test_validation_error_does_not_leak_identification() -> None:
    with pytest.raises(ValidationError) as info:
        IdentificationInput.model_validate({"identification": ID, "copy_evidence": "x"})
    assert ID not in str(info.value)


# --- CopyEvidence --------------------------------------------------------------------------


@pytest.mark.parametrize("responsible", ["USR-001", "ab", "a.b_c-9", "A" * 40])
def test_responsible_code_is_accepted(responsible: str) -> None:
    assert _evidence(responsible).responsible == responsible


@pytest.mark.parametrize("responsible", ["Juan Perez", "juan perez gomez", "usr 001", "usr@001"])
def test_responsible_full_name_with_spaces_is_rejected(responsible: str) -> None:
    with pytest.raises(InvalidIdentification) as info:
        _evidence(responsible)
    assert info.value.reason is InvalidReason.INVALID_RESPONSIBLE
    assert responsible not in str(info.value)


@pytest.mark.parametrize("responsible", ["", "q", "q" * 41, "ñandú"])
def test_responsible_wrong_length_or_charset_is_rejected(responsible: str) -> None:
    with pytest.raises(InvalidIdentification) as info:
        _evidence(responsible)
    assert info.value.reason is InvalidReason.INVALID_RESPONSIBLE
    if responsible:
        assert responsible not in str(info.value)


def test_non_str_responsible_is_rejected() -> None:
    with pytest.raises(InvalidIdentification) as info:
        CopyEvidence.model_validate({"copy_date": COPY_DATE, "responsible": 123})
    assert info.value.reason is InvalidReason.INVALID_RESPONSIBLE


@pytest.mark.parametrize("raw", [COPY_DATE, "2026-09-09"])
def test_copy_date_accepts_date_and_iso_string(raw: object) -> None:
    evidence = CopyEvidence.model_validate({"copy_date": raw, "responsible": "USR-001"})
    assert evidence.copy_date == COPY_DATE


@pytest.mark.parametrize(
    "raw",
    [
        "ilegible",
        "",
        "09/09/2026",
        "2026-13-40",
        "2026-0909",
        0,
        1790000000,
        1.5,
        True,
        None,
        datetime(2026, 9, 9, 8, 0, tzinfo=UTC),
    ],
)
def test_copy_date_unreadable_is_rejected(raw: object) -> None:
    with pytest.raises(InvalidIdentification) as info:
        CopyEvidence.model_validate({"copy_date": raw, "responsible": "USR-001"})
    assert info.value.reason is InvalidReason.UNREADABLE_COPY_DATE


def test_evidence_repr_hides_responsible() -> None:
    text = repr(_evidence())
    assert "USR-001" not in text
    assert "copy_date" in text


def test_note_200_chars_is_accepted() -> None:
    assert IdentificationInput(identification=ID, note="x" * 200).note == "x" * 200


def test_note_over_200_chars_is_rejected() -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput(identification=ID, note="x" * 201)
    assert info.value.reason is InvalidReason.OBSERVATION_TOO_LONG


# --- RutResult -----------------------------------------------------------------------------


def test_validada_copia_without_estado_nor_name_is_valid() -> None:
    result = _validada(observation="Validado contra copia del RUT")
    assert result.estado_rut == ""
    assert result.name == ""


@pytest.mark.parametrize("field", ["estado_rut", "name"])
@pytest.mark.parametrize("value", [NAME, "   "])
def test_validada_copia_rejects_estado_or_name(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as info:
        _validada(**{field: value})
    assert NAME not in str(info.value)


@pytest.mark.parametrize("source", [SourceKind.PORTAL_DIAN_C1, SourceKind.SIN_CONSULTA])
def test_validada_copia_requires_copy_source(source: SourceKind) -> None:
    with pytest.raises(ValidationError):
        RutResult(status=QueryStatus.VALIDADA_COPIA_RUT, source=source)


@pytest.mark.parametrize("source", [SourceKind.PORTAL_DIAN_C1, SourceKind.COPIA_RUT_TERCERO])
def test_entrada_invalida_requires_sin_consulta(source: SourceKind) -> None:
    with pytest.raises(ValidationError):
        RutResult(status=QueryStatus.ENTRADA_INVALIDA, source=source)
    ok = RutResult(status=QueryStatus.ENTRADA_INVALIDA, source=SourceKind.SIN_CONSULTA)
    assert ok.source is SourceKind.SIN_CONSULTA


@pytest.mark.parametrize("field", ["estado_rut", "name"])
@pytest.mark.parametrize(
    "source",
    [SourceKind.CONTINGENCIA_MANUAL, SourceKind.COPIA_RUT_TERCERO, SourceKind.SIN_CONSULTA],
)
def test_estado_or_name_only_from_portal_or_fake(field: str, source: SourceKind) -> None:
    with pytest.raises(ValidationError):
        RutResult(status=QueryStatus.PENDIENTE_VALIDACION_MANUAL, source=source, **{field: NAME})


@pytest.mark.parametrize("source", [SourceKind.PORTAL_DIAN_C1, SourceKind.FAKE])
def test_estado_and_name_allowed_from_portal_or_fake(source: SourceKind) -> None:
    result = RutResult(status=QueryStatus.SIN_RESULTADOS, source=source, estado_rut="X", name=NAME)
    assert result.name == NAME


def test_exitosa_without_estado_raises_incomplete() -> None:
    with pytest.raises(IncompleteResult):
        RutResult(status=QueryStatus.EXITOSA, source=SourceKind.PORTAL_DIAN_C1, name=NAME)


def test_exitosa_with_blank_estado_raises_incomplete() -> None:
    with pytest.raises(IncompleteResult):
        RutResult(status=QueryStatus.EXITOSA, source=SourceKind.PORTAL_DIAN_C1, estado_rut="  ")


def test_exitosa_with_estado_is_valid() -> None:
    result = RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.PORTAL_DIAN_C1,
        estado_rut="REGISTRO ACTIVO",
        name=NAME,
    )
    assert result.estado_rut == "REGISTRO ACTIVO"


def test_result_repr_hides_name_and_observation() -> None:
    result = RutResult(
        status=QueryStatus.EXITOSA,
        source=SourceKind.PORTAL_DIAN_C1,
        estado_rut="REGISTRO ACTIVO",
        name=NAME,
        observation="obs privada",
    )
    text = repr(result)
    assert NAME not in text
    assert "obs privada" not in text
    assert "EXITOSA" in text


# --- InputRow ------------------------------------------------------------------------------


def _row(**overrides: object) -> InputRow:
    base: dict[str, object] = {
        "row_index": 3,
        "raw_identification": ID,
        "raw_dv": "7",
        "raw_copy_date": "2026-09-09",
        "raw_responsible": "Juan Perez Gomez",
        "raw_note": "nota privada",
    }
    base.update(overrides)
    return InputRow.model_validate(base)


def test_input_row_repr_masks_identification_and_hides_rest() -> None:
    row = _row()
    for text in (repr(row), str(row)):
        assert ID not in text
        assert "******0001" in text
        assert "Juan Perez" not in text
        assert "nota privada" not in text
        assert "2026-09-09" not in text


def test_input_row_accepts_missing_and_garbage_values() -> None:
    row = InputRow(row_index=0)
    assert row.raw_identification is None
    assert "12A45" not in repr(_row(raw_identification="12A45"))


def test_input_row_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        _row(row_index=-1)


# --- QueryOutcome --------------------------------------------------------------------------


def _outcome(**overrides: object) -> QueryOutcome:
    base: dict[str, object] = {
        "row": _row(),
        "identification": IdentificationInput(identification=ID, note="privada"),
        "result": _validada(),
        "queried_at": datetime(2026, 10, 9, 8, 0, tzinfo=UTC),
        "duration_ms": 12,
    }
    base.update(overrides)
    return QueryOutcome.model_validate(base)


def test_outcome_repr_masks_identification() -> None:
    outcome = _outcome()
    for text in (repr(outcome), str(outcome)):
        assert ID not in text
        assert "******0001" in text
        assert "privada" not in text


def test_outcome_for_invalid_row_has_no_identification_input() -> None:
    outcome = _outcome(
        row=_row(raw_identification="12A45", raw_copy_date="ilegible"),
        identification=None,
        result=RutResult(status=QueryStatus.ENTRADA_INVALIDA, source=SourceKind.SIN_CONSULTA),
    )
    assert outcome.identification is None
    assert outcome.result.status is QueryStatus.ENTRADA_INVALIDA


def test_outcome_without_identification_requires_entrada_invalida() -> None:
    with pytest.raises(ValidationError):
        _outcome(identification=None)


def test_outcome_from_dict_propagates_nested_invalid_identification() -> None:
    with pytest.raises(InvalidIdentification) as info:
        _outcome(identification={"identification": "12A45"})
    assert info.value.reason is InvalidReason.NON_NUMERIC


def test_outcome_requires_aware_datetime() -> None:
    with pytest.raises(ValidationError):
        _outcome(queried_at=datetime(2026, 10, 9, 8, 0))  # prueba de fecha ingenua


def test_outcome_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        _outcome(duration_ms=-1)


def test_non_str_note_is_rejected_with_closed_reason() -> None:
    with pytest.raises(InvalidIdentification) as info:
        IdentificationInput.model_validate({"identification": ID, "note": 5})
    assert info.value.reason is InvalidReason.OBSERVATION_TOO_LONG


def test_sin_consulta_requires_entrada_invalida() -> None:
    with pytest.raises(ValidationError):
        RutResult(status=QueryStatus.PENDIENTE_VALIDACION_MANUAL, source=SourceKind.SIN_CONSULTA)


@pytest.mark.parametrize(
    "source",
    [SourceKind.CONTINGENCIA_MANUAL, SourceKind.COPIA_RUT_TERCERO, SourceKind.SIN_CONSULTA],
)
def test_exitosa_requires_portal_or_fake_before_incomplete(source: SourceKind) -> None:
    with pytest.raises(ValidationError):
        RutResult(status=QueryStatus.EXITOSA, source=source)


def test_outcome_entrada_invalida_may_keep_identification() -> None:
    outcome = _outcome(
        result=RutResult(status=QueryStatus.ENTRADA_INVALIDA, source=SourceKind.SIN_CONSULTA)
    )
    assert outcome.identification is not None
