"""Pruebas del enmascarado de identificaciones (CLAUDE.md §4)."""

import pytest

from rut_checker.domain.masking import mask_digit_runs, mask_identification


def test_masks_all_but_last_four() -> None:
    assert mask_identification("1234567890") == "******7890"


@pytest.mark.parametrize("value", ["1234", "123", "1", "12345", "123456", "ab123"])
def test_short_values_are_fully_masked(value: str) -> None:
    assert mask_identification(value) == "*" * len(value)


def test_empty_value_stays_empty() -> None:
    assert mask_identification("") == ""


def test_masks_dotted_and_spaced_ids() -> None:
    assert mask_identification("1.000.000.001") == "******0001"
    assert mask_identification("900 000 001-7") == "******0017"
    assert mask_identification(" 123456789 ") == "*****6789"


def test_mask_never_leaks_more_than_four_chars() -> None:
    masked = mask_identification("1234567890")
    assert masked.count("*") == 6
    assert "123456" not in masked


def test_mask_digit_runs_in_free_text() -> None:
    text = "falló la fila con 1.000.000.001 y con 900 000 001-7 fin"
    result = mask_digit_runs(text)
    assert "1.000.000.001" not in result
    assert "900 000 001" not in result
    assert "******0001" in result
    assert result.startswith("falló la fila con ")
    assert result.endswith(" fin")


def test_mask_digit_runs_leaves_short_numbers() -> None:
    assert mask_digit_runs("intento 3 de 12 (fila 45)") == "intento 3 de 12 (fila 45)"


def test_mask_digit_runs_masks_iso_dates_too() -> None:
    # Aceptado (P2): el regex también casa fechas ISO en texto libre.
    assert "2026-10-09" not in mask_digit_runs("fecha 2026-10-09")


def test_mask_digit_runs_is_idempotent() -> None:
    once = mask_digit_runs("id 1234567890")
    assert mask_digit_runs(once) == once


def test_seven_chars_show_last_four() -> None:
    assert mask_identification("1234567") == "***4567"
    assert mask_identification("900000001") == "*****0001"


def test_letters_are_masked_like_digits() -> None:
    assert mask_identification("AB1234567") == "*****4567"


def test_only_separators_gives_single_star() -> None:
    assert mask_identification(" .- ") == "*"


def test_long_string_keeps_only_last_four() -> None:
    assert mask_identification("1" * 30) == "*" * 26 + "1111"


def test_mask_digit_runs_does_not_join_lines() -> None:
    result = mask_digit_runs("1234567890" + chr(10) + "1000000001")
    assert result == "******7890" + chr(10) + "******0001"


def test_mask_digit_runs_handles_slashes() -> None:
    assert mask_digit_runs("nit 900/000/001 ok") == "nit *****0001 ok"


def test_mask_digit_runs_several_ids() -> None:
    # Ids separados por ", " se funden en una sola secuencia; lo importante es no filtrar ninguno.
    result = mask_digit_runs("1234567890, 1000000001")
    assert "1234567" not in result
    assert "1000000" not in result
    assert result.endswith("0001")
    assert mask_digit_runs("1234567890 y 1000000001") == "******7890 y ******0001"


def test_mask_digit_runs_short_ids_not_masked() -> None:
    # Cédulas sueltas de 3-5 dígitos no se enmascaran (límite documentado).
    assert mask_digit_runs("cedula 12345 fin") == "cedula 12345 fin"


def test_mask_digit_runs_handles_tabs_and_underscores() -> None:
    assert mask_digit_runs("nit 900" + chr(9) + "000" + chr(9) + "001 ok") == "nit *****0001 ok"
    assert mask_digit_runs("id 1_000_000_001 ok") == "id ******0001 ok"
