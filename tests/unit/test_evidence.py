"""Pruebas de la regla de vigencia de la copia del RUT (G9, G10)."""

from datetime import date, timedelta

import pytest

from rut_checker.domain.evidence import MAX_COPY_AGE_DAYS, CopyVerdict, evaluate_copy_evidence
from rut_checker.domain.models import CopyEvidence

TODAY = date(2026, 10, 9)


def _evidence(age_days: int) -> CopyEvidence:
    return CopyEvidence(copy_date=TODAY - timedelta(days=age_days), responsible="USR-001")


def test_max_age_constant_is_30() -> None:
    assert MAX_COPY_AGE_DAYS == 30


def test_copy_30_days_old_is_validada_copia_rut() -> None:
    assert evaluate_copy_evidence(_evidence(30), TODAY) is CopyVerdict.VALID


def test_copy_31_days_old_is_expired() -> None:
    assert evaluate_copy_evidence(_evidence(31), TODAY) is CopyVerdict.EXPIRED


@pytest.mark.parametrize("age", [0, 1, 29])
def test_recent_copies_are_valid(age: int) -> None:
    assert evaluate_copy_evidence(_evidence(age), TODAY) is CopyVerdict.VALID


def test_very_old_copy_is_expired() -> None:
    assert evaluate_copy_evidence(_evidence(4000), TODAY) is CopyVerdict.EXPIRED


def test_future_date_is_invalid() -> None:
    assert evaluate_copy_evidence(_evidence(-1), TODAY) is CopyVerdict.FUTURE_DATE
