"""Pruebas de la jerarquía de errores de dominio."""

import pytest

from rut_checker.domain import errors
from rut_checker.domain.errors import (
    InvalidFileReason,
    InvalidIdentification,
    InvalidInputFile,
    InvalidReason,
    RutCheckerError,
)

GENERIC_ERRORS: list[type[RutCheckerError]] = [
    errors.PortalUnavailable,
    errors.QueryTimeout,
    errors.SessionExpired,
    errors.StructureChanged,
    errors.IncompleteResult,
    errors.HumanInterventionRequired,
    errors.AccessBlocked,
    errors.ExportError,
    errors.SourceNotEnabledError,
    errors.SelectorsNotValidatedError,
    errors.FakeNotAllowedError,
]


@pytest.mark.parametrize("cls", GENERIC_ERRORS)
def test_generic_errors_have_spanish_message_and_base(cls: type[RutCheckerError]) -> None:
    exc = cls()
    assert isinstance(exc, RutCheckerError)
    assert str(exc)
    assert not any(ch.isdigit() for ch in str(exc))


def test_str_never_contains_full_id() -> None:
    exc = InvalidIdentification(InvalidReason.NON_NUMERIC)
    assert "1234567890" not in str(exc)
    assert "1234567890" not in repr(exc)
    assert InvalidReason.NON_NUMERIC.value in str(exc)
    assert exc.reason is InvalidReason.NON_NUMERIC


def test_reason_rejects_free_text() -> None:
    with pytest.raises(TypeError, match="motivo"):
        InvalidIdentification("valor 1234567890 inválido")  # type: ignore[arg-type]  # prueba intencional de tipo inválido


def test_reason_set_is_closed_and_digit_free() -> None:
    for reason in InvalidReason:
        assert not any(ch.isdigit() for ch in reason.value)


@pytest.mark.parametrize("cls", GENERIC_ERRORS)
def test_generic_errors_reject_custom_message(cls: type[RutCheckerError]) -> None:
    with pytest.raises(TypeError):
        cls("1234567890")  # type: ignore[call-arg]  # prueba intencional: mensaje propio no permitido


def test_invalid_input_file_keeps_closed_reason() -> None:
    exc = InvalidInputFile(InvalidFileReason.TOO_MANY_ROWS)
    assert exc.reason is InvalidFileReason.TOO_MANY_ROWS
    assert InvalidFileReason.TOO_MANY_ROWS.value in str(exc)


def test_invalid_input_file_rejects_free_text() -> None:
    with pytest.raises(TypeError, match="motivo"):
        InvalidInputFile("C:/datos/1234567890.xlsx")  # type: ignore[arg-type]  # prueba intencional


def test_file_reason_set_is_digit_free() -> None:
    for reason in InvalidFileReason:
        assert not any(ch.isdigit() for ch in reason.value)


def test_new_file_reasons_exist() -> None:
    names = {r.name for r in InvalidFileReason}
    assert {"DUPLICATE_COLUMN", "FIRST_SHEET_HIDDEN", "TOO_MANY_RAW_ROWS"} <= names
    assert "DUPLICATE_ID_COLUMN" not in names


def test_unsafe_path_error_keeps_closed_reason() -> None:
    exc = errors.UnsafePathError(errors.UnsafePathReason.INSIDE_GIT_TREE)
    assert exc.reason is errors.UnsafePathReason.INSIDE_GIT_TREE
    assert errors.UnsafePathReason.INSIDE_GIT_TREE.value in str(exc)


def test_unsafe_path_error_rejects_free_text() -> None:
    with pytest.raises(TypeError, match="motivo"):
        errors.UnsafePathError("C:/datos/1234567890")  # type: ignore[arg-type]  # prueba intencional
