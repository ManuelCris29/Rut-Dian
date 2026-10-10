"""Pruebas de normalización y validación de identificaciones (T-41)."""

import pytest

from rut_checker.domain.errors import InvalidIdentification, InvalidReason
from rut_checker.domain.validators import normalize_identification, validate_identification

CEDULA = "1000000001"
_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def _reference_dv(number: str) -> str:
    """Algoritmo módulo 11 de la DIAN, implementado de forma independiente de stdnum."""
    total = sum(int(d) * w for d, w in zip(reversed(number), _WEIGHTS, strict=False)) % 11
    return str(total if total in (0, 1) else 11 - total)


def _reason(raw: object, dv: str | None = None) -> InvalidReason:
    with pytest.raises(InvalidIdentification) as info:
        validate_identification(raw, dv)
    return info.value.reason


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" 1000000001 ", (CEDULA, None)),
        ("1.000.000.001", (CEDULA, None)),
        ("1,000,000,001", (CEDULA, None)),
        ("1 000 000 001", (CEDULA, None)),
        (1000000001.0, (CEDULA, None)),
        (1000000001, (CEDULA, None)),
        ("900.000.001-7", ("900000001", "7")),
        ("900000001 - 7", ("900000001", "7")),
    ],
)
def test_normalizes_accepted_formats(raw: object, expected: tuple[str, str | None]) -> None:
    assert normalize_identification(raw) == expected


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, InvalidReason.EMPTY),
        ("", InvalidReason.EMPTY),
        ("   ", InvalidReason.EMPTY),
        ("12A45", InvalidReason.NON_NUMERIC),
        (chr(0x661) + chr(0x662), InvalidReason.NON_NUMERIC),  # dígitos arábigo-índicos
        ("1E9", InvalidReason.NON_NUMERIC),
        ("-1000000001", InvalidReason.NON_NUMERIC),
        ("1-2-3", InvalidReason.NON_NUMERIC),
        ("900000001-", InvalidReason.NON_NUMERIC),
        (1000000001.5, InvalidReason.NON_NUMERIC),
        (1e30, InvalidReason.LENGTH_OUT_OF_RANGE),
        (float("nan"), InvalidReason.NON_NUMERIC),
        (float("inf"), InvalidReason.NON_NUMERIC),
        (-5, InvalidReason.NON_NUMERIC),
        (True, InvalidReason.NON_NUMERIC),
        (b"1000000001", InvalidReason.NON_NUMERIC),
        ("900000001-77", InvalidReason.BAD_CHECK_DIGIT),
        ("900000001-A", InvalidReason.BAD_CHECK_DIGIT),
    ],
)
def test_normalize_rejects_malformed_input(raw: object, reason: InvalidReason) -> None:
    with pytest.raises(InvalidIdentification) as info:
        normalize_identification(raw)
    assert info.value.reason is reason


def test_rejects_non_numeric() -> None:
    assert _reason("12A45") is InvalidReason.NON_NUMERIC


def test_rejects_empty() -> None:
    assert _reason("") is InvalidReason.EMPTY


@pytest.mark.parametrize("raw", ["12", "1" * 11, "1" * 12])
def test_rejects_length_out_of_range(raw: str) -> None:
    assert _reason(raw) is InvalidReason.LENGTH_OUT_OF_RANGE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123", "123"),
        ("12345678", "12345678"),
        ("123456789", "123456789"),
        ("1234567890", "1234567890"),
        (CEDULA, CEDULA),
        (1000000001.0, CEDULA),
    ],
)
def test_accepts_valid_lengths_without_dv(raw: object, expected: str) -> None:
    result = validate_identification(raw, None)
    assert result.dv is None
    assert result.identification == expected


def test_no_dv_means_no_dv_check() -> None:
    """Sin DV (columna ni sufijo) no se calcula ni se exige (P-4)."""
    assert validate_identification("900000001", None).dv is None
    assert validate_identification("900000001", "").dv is None
    assert validate_identification("900000001", "  ").dv is None


@pytest.mark.parametrize("length", range(3, 11))
@pytest.mark.parametrize("k", range(1, 6))
def test_dv_matches_reference_algorithm(length: int, k: int) -> None:
    """Propiedad: bases generadas (3 a 10 dígitos) contra el algoritmo de referencia."""
    base = str(10 ** (length - 1) + k * 7919 % (9 * 10 ** (length - 1)))
    assert len(base) == length
    expected = _reference_dv(base)
    by_column = validate_identification(base, expected)
    assert (by_column.identification, by_column.dv) == (base, expected)
    by_suffix = validate_identification(f"{base}-{expected}", None)
    assert (by_suffix.identification, by_suffix.dv) == (base, expected)
    both = validate_identification(f"{base}-{expected}", expected)
    assert both.dv == expected


@pytest.mark.parametrize("suffix", ["", ".0"])
def test_dv_accepts_excel_numeric_text(suffix: str) -> None:
    expected = _reference_dv("900000001")
    assert validate_identification("900000001", expected + suffix).dv == expected


@pytest.mark.parametrize("last", range(1, 10))
def test_wrong_dv_is_invalid(last: int) -> None:
    base = f"90000000{last}"
    wrong = str((int(_reference_dv(base)) + 1) % 10)
    assert _reason(base, wrong) is InvalidReason.BAD_CHECK_DIGIT
    assert _reason(f"{base}-{wrong}") is InvalidReason.BAD_CHECK_DIGIT


def test_conflicting_suffix_and_column_dv_is_invalid() -> None:
    right = _reference_dv("900000001")
    other = str((int(right) + 1) % 10)
    assert _reason(f"900000001-{right}", other) is InvalidReason.BAD_CHECK_DIGIT


@pytest.mark.parametrize("dv", ["77", "A", "-1", chr(0x667)])
def test_malformed_dv_column_is_invalid(dv: str) -> None:
    assert _reason("900000001", dv) is InvalidReason.BAD_CHECK_DIGIT


def test_dv_on_cedula_length_is_also_checked() -> None:
    wrong = str((int(_reference_dv(CEDULA)) + 1) % 10)
    assert _reason(CEDULA, wrong) is InvalidReason.BAD_CHECK_DIGIT


def test_length_is_checked_before_dv() -> None:
    assert _reason("1" * 11, "0") is InvalidReason.LENGTH_OUT_OF_RANGE


@pytest.mark.parametrize(
    "raw", ["12A45-9", "", "1" * 11, "900000001-77", "secreto ABC", 1000000001.5]
)
def test_reason_never_contains_raw_value(raw: object) -> None:
    with pytest.raises(InvalidIdentification) as info:
        validate_identification(raw, "9")
    exc = info.value
    for text in (str(exc), repr(exc), exc.reason.value):
        assert "12A45" not in text
        assert "1111" not in text
        assert "secreto" not in text
        assert "900000001" not in text
        assert "1000000001" not in text


def test_excel_float_precision_limit() -> None:
    """Flotantes enteros que superan 2**53 pierden dígitos: se rechazan por longitud."""
    assert _reason(float(2**53 + 2)) is InvalidReason.LENGTH_OUT_OF_RANGE


@pytest.mark.parametrize("last", range(1, 10))
def test_dv_of_whitelisted_nits(last: int) -> None:
    base = f"90000000{last}"
    expected = _reference_dv(base)
    assert validate_identification(base, expected).dv == expected


@pytest.mark.parametrize(
    "raw",
    [
        "12.34",
        "1,2,3",
        "1.000,000",
        "1.00.000",
        "1..000",
        ".5",
        "5.",
        "900.000 000",
        "1 000.000",
        "900 000.000",
        "1 000,000",
        "1 000 000.0",
        "12345678.000",
    ],
)
def test_misplaced_or_ambiguous_separators_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidIdentification) as info:
        normalize_identification(raw)
    assert info.value.reason is InvalidReason.NON_NUMERIC


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("900000001.0", ("900000001", None)),
        ("12345678,0", ("12345678", None)),
        ("12345678.00", ("12345678", None)),
        ("12345678,00", ("12345678", None)),
        ("900000001.0-2", ("900000001", "2")),
        (" 900000001 - 7 ", ("900000001", "7")),
        ("100.000.000", ("100000000", None)),
        ("1 000 000 001", (CEDULA, None)),
        ("1.000", ("1000", None)),
        ("1,000", ("1000", None)),
        ("900.000.001-7", ("900000001", "7")),
    ],
)
def test_valid_separators(raw: str, expected: tuple[str, str | None]) -> None:
    assert normalize_identification(raw) == expected


def test_nbsp_is_whitespace() -> None:
    assert normalize_identification("\u00a01000000001\u00a0") == (CEDULA, None)


def test_ten_digits_without_separator_is_not_split() -> None:
    assert normalize_identification("1234567890") == ("1234567890", None)


@pytest.mark.parametrize("code", [0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212])
def test_unicode_dashes_separate_dv(code: int) -> None:
    assert normalize_identification(f"900000001{chr(code)}7") == ("900000001", "7")


def test_huge_int_is_length_error() -> None:
    assert _reason(10**30) is InvalidReason.LENGTH_OUT_OF_RANGE


@pytest.mark.parametrize("raw", ["0", "000", 0, "0" * 10])
def test_all_zeros_is_rejected(raw: object) -> None:
    assert _reason(raw) is InvalidReason.LENGTH_OUT_OF_RANGE


@pytest.mark.parametrize(
    "raw",
    ["900000001 7", "900 000 001 7", "1000 000 001", "1  000 000", "10 00", "1 0000 000"],
)
def test_badly_grouped_spaces_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidIdentification) as info:
        normalize_identification(raw)
    assert info.value.reason is InvalidReason.NON_NUMERIC


def test_unicode_spaces_group_thousands() -> None:
    spaced = f"1{chr(0xA0)}000{chr(0x2009)}000{chr(0x202F)}001"
    assert normalize_identification(spaced) == (CEDULA, None)


def test_spaces_around_dv_hyphen_are_kept_accepted() -> None:
    """El DV lo une el guion explícito; los espacios alrededor son solo formato."""
    assert normalize_identification("900.000.001 - 7") == ("900000001", "7")


def _glued(base: str, dv: str) -> str:
    return base + dv


@pytest.mark.parametrize("last", range(1, 10))
def test_glued_check_digit_is_flagged(last: int) -> None:
    base = f"90000000{last}"
    result = validate_identification(_glued(base, _reference_dv(base)), None)
    assert result.possible_glued_check_digit is True
    assert result.dv is None


def test_glued_check_digit_not_flagged_when_it_does_not_match() -> None:
    base = "900000001"
    wrong = str((int(_reference_dv(base)) + 1) % 10)
    assert validate_identification(base + wrong, None).possible_glued_check_digit is False


def test_glued_check_digit_not_flagged_when_dv_arrives_or_other_shapes() -> None:
    base = "900000001"
    dv = _reference_dv(base)
    assert validate_identification(base, dv).possible_glued_check_digit is False
    assert validate_identification(CEDULA, None).possible_glued_check_digit is False
    assert validate_identification(base, None).possible_glued_check_digit is False
    # 10 dígitos que no empiezan por 8 ni 9 no se marcan aunque coincida el DV
    ten = "100000000"
    assert (
        validate_identification(ten + _reference_dv(ten), None).possible_glued_check_digit is False
    )
