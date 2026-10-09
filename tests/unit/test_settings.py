"""Pruebas de `Settings` (ARQUITECTURA §9, ADR-0002 §3, G12).

Aislamiento: `Settings(_env_file=None)` impide leer el `.env` real del repositorio (que
nunca se lee en pruebas) y la fixture `clean_env` elimina cualquier variable `RUT_*` heredada
del entorno del desarrollador, de modo que cada prueba parte de los valores por defecto.
"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from rut_checker.infra.settings import Settings

VALID_REF = "APR-20261009-1"
DIAN_URL = "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Elimina toda variable `RUT_*` del entorno antes de cada prueba."""
    for name in list(os.environ):
        if name.upper().startswith("RUT_"):
            monkeypatch.delenv(name)


def load() -> Settings:
    """Construye `Settings` sin leer ningún archivo `.env`."""
    return Settings(_env_file=None)


def test_defaults_are_safe() -> None:
    settings = load()
    assert settings.source == "contingency"
    assert settings.portal_enabled is False
    assert settings.allow_fake is False
    assert settings.diagnostic_snapshot is False
    assert settings.headless is False
    assert settings.portal_approval_ref == ""
    assert settings.min_delay_between_queries_s == 5
    assert settings.portal_url == DIAN_URL
    assert settings.retry_backoff_s == (30, 120)
    assert settings.output_dir == Path("output")


def test_env_vars_are_read_with_rut_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_MAX_RETRIES", "1")
    monkeypatch.setenv("RUT_RETRY_BACKOFF_S", "10, 20")
    monkeypatch.setenv("RUT_SOURCE", "fake")
    monkeypatch.setenv("RUT_ALLOW_FAKE", "true")
    settings = load()
    assert settings.max_retries == 1
    assert settings.retry_backoff_s == (10, 20)
    assert settings.source == "fake"
    assert settings.allow_fake is True


def test_env_file_of_repo_is_not_read_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("RUT_MAX_RETRIES=1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load().max_retries == 2


def test_delay_below_3_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_MIN_DELAY_BETWEEN_QUERIES_S", "2.9")
    with pytest.raises(ValidationError):
        load()


def test_delay_of_3_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_MIN_DELAY_BETWEEN_QUERIES_S", "3")
    assert load().min_delay_between_queries_s == 3


def test_dian_portal_requires_headed_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_SOURCE", "dian_portal")
    monkeypatch.setenv("RUT_HEADLESS", "true")
    with pytest.raises(ValidationError, match="headless"):
        load()


def test_headless_is_allowed_for_other_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_HEADLESS", "true")
    assert load().headless is True


def test_dian_portal_with_headed_browser_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_SOURCE", "dian_portal")
    assert load().source == "dian_portal"


@pytest.mark.parametrize(
    "ref", ["APR-2026100-1", "apr-20261009-1", "APR-20261009-", "APR-20261009-1234", "X", " "]
)
def test_approval_ref_bad_format_rejected(monkeypatch: pytest.MonkeyPatch, ref: str) -> None:
    monkeypatch.setenv("RUT_PORTAL_APPROVAL_REF", ref)
    with pytest.raises(ValidationError):
        load()


def test_approval_ref_with_impossible_date_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_PORTAL_APPROVAL_REF", "APR-20269999-1")
    with pytest.raises(ValidationError):
        load()


@pytest.mark.parametrize("ref", ["", VALID_REF, "APR-20261009-123"])
def test_approval_ref_valid_format_accepted(monkeypatch: pytest.MonkeyPatch, ref: str) -> None:
    monkeypatch.setenv("RUT_PORTAL_APPROVAL_REF", ref)
    assert load().portal_approval_ref == ref


@pytest.mark.parametrize(
    "url",
    [
        "http://muisca.dian.gov.co/x",
        "https://evil-dian.gov.co/x",
        "https://dian.gov.co.evil.com/x",
        "https://muisca.dian.gov.co@evil.com/x",
        "https://example.com/",
        "https://dian.gov.co/",
        "ftp://muisca.dian.gov.co/",
        "muisca.dian.gov.co",
        "",
        r"https://evil.com\.dian.gov.co/x",
        "https://:pw@muisca.dian.gov.co/x",
        "https://user@muisca.dian.gov.co/x",
        "https://muisca.dian.gov.co:8443/x",
        "https://muisca.dian.gov.co:abc/x",
        "https://.dian.gov.co/",
        "https://-a.dian.gov.co/",
        " https://muisca.dian.gov.co/x",
        "https://muisca.dian.gov.co/x\t",
        "https://muisca.dian.gov.co/a b",
        "https://evil.com%5C.dian.gov.co/x",
        "https://evil.com%2F.dian.gov.co/x",
        "https://muisca.dian.gov.co./x",
        "https://m\u00faisca.dian.gov.co/x",
        "https://muisca\u3002dian.gov.co/x",
        "https://evil.com\uff0f.dian.gov.co/x",
        "https://muisca.dian.gov.co:0/x",
        "https://muisca.dian.gov.co/\x7f",
    ],
)
def test_portal_url_http_or_foreign_host_rejected(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("RUT_PORTAL_URL", url)
    with pytest.raises(ValidationError):
        load()


def test_portal_url_empty_port_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_PORTAL_URL", "https://muisca.dian.gov.co:/x")
    assert load().portal_url == "https://muisca.dian.gov.co:/x"


def test_portal_url_explicit_443_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_PORTAL_URL", "https://muisca.dian.gov.co:443/x")
    assert load().portal_url.endswith(":443/x")


@pytest.mark.parametrize(
    "url", [DIAN_URL, "https://MUISCA.DIAN.GOV.CO/x", "https://www.dian.gov.co/"]
)
def test_portal_url_dian_host_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("RUT_PORTAL_URL", url)
    assert load().portal_url == url


def test_snapshot_without_ref_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_DIAGNOSTIC_SNAPSHOT", "true")
    with pytest.raises(ValidationError, match="APPROVAL_REF"):
        load()


def test_snapshot_with_valid_ref_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_DIAGNOSTIC_SNAPSHOT", "true")
    monkeypatch.setenv("RUT_PORTAL_APPROVAL_REF", VALID_REF)
    assert load().diagnostic_snapshot is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RUT_MAX_RETRIES", "3"),
        ("RUT_MAX_RETRIES", "-1"),
        ("RUT_HUMAN_CHALLENGE_TIMEOUT_S", "29"),
        ("RUT_HUMAN_CHALLENGE_TIMEOUT_S", "901"),
        ("RUT_MAX_BATCH_SIZE", "0"),
        ("RUT_MAX_BATCH_SIZE", "201"),
        ("RUT_RETENTION_DAYS", "366"),
        ("RUT_RETENTION_DAYS", "0"),
        ("RUT_NAVIGATION_TIMEOUT_S", "0"),
        ("RUT_RETRY_BACKOFF_S", "0,5"),
        ("RUT_SOURCE", "portal"),
        ("RUT_MIN_DELAY_BETWEEN_QUERIES_S", "inf"),
        ("RUT_MIN_DELAY_BETWEEN_QUERIES_S", "nan"),
        ("RUT_MIN_DELAY_BETWEEN_QUERIES_S", "601"),
        ("RUT_RETRY_BACKOFF_S", ""),
        ("RUT_RETRY_BACKOFF_S", "30"),
        ("RUT_RETRY_BACKOFF_S", "1,120"),
    ],
)
def test_out_of_range_values_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        load()


def test_empty_backoff_accepted_without_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUT_MAX_RETRIES", "0")
    monkeypatch.setenv("RUT_RETRY_BACKOFF_S", "")
    assert load().retry_backoff_s == ()


def test_settings_are_immutable() -> None:
    settings = load()
    with pytest.raises(ValidationError):
        settings.max_retries = 1  # type: ignore[misc]  # asignación intencional a modelo frozen
