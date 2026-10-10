"""`silence_unconfigured_loggers`: un logger de terceros no escribe a stderr (T-43/T-35)."""

import logging
from pathlib import Path

import pytest

from rut_checker.infra.logging import (
    close_run_logging,
    configure_logging,
    silence_unconfigured_loggers,
)

FULL_ID = "1000000001"


def _bare_root(monkeypatch: pytest.MonkeyPatch) -> logging.Logger:
    """Root sin handlers (como en producción): así actúa `lastResort`.

    Pytest instala los suyos en cada fase: debe llamarse dentro de la prueba, porque la fase
    `call` los reinstala después de las fixtures.
    """
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    return root


def test_control_unconfigured_logger_reaches_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _bare_root(monkeypatch)
    logging.getLogger("tercero").warning("id %s", FULL_ID)
    assert FULL_ID in capsys.readouterr().err  # sin la función, el id saldría por stderr


def test_unconfigured_logger_is_silent_after_silencing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _bare_root(monkeypatch)
    silence_unconfigured_loggers()
    logging.getLogger("tercero").warning("id %s", FULL_ID)
    logging.getLogger("tercero").error("id %s", FULL_ID)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_silencing_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _bare_root(monkeypatch)
    silence_unconfigured_loggers()
    silence_unconfigured_loggers()
    assert sum(isinstance(h, logging.NullHandler) for h in root.handlers) == 1


def test_close_run_logging_releases_the_log_file(tmp_path: Path) -> None:
    run_id = "20261010-130000-beef"
    logger = configure_logging(run_id, tmp_path)
    logger.info("run_started")
    close_run_logging(run_id)
    close_run_logging(run_id)  # idempotente
    assert not [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    (tmp_path / f"run_{run_id}.jsonl").unlink()  # en Windows falla si el archivo sigue abierto


def test_close_run_logging_rejects_bad_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        close_run_logging("../../x")
