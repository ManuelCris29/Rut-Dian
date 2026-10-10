"""Pruebas del logging JSONL con enmascarado (ARQUITECTURA §10, CLAUDE.md §4)."""

import json
import logging
import sys
import warnings
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Final

import pytest

from rut_checker.domain.masking import mask_identification
from rut_checker.infra.logging import (
    LogEvent,
    MaskingFilter,
    close_logging,
    configure_logging,
    log_exception,
)

RUN_ID: Final = "20261009-101500-ab12"
FULL_ID: Final = "1000000001"
ALLOWED_FIELDS: Final = {
    "ts",
    "event",
    "run_id",
    "row_index",
    "id_masked",
    "source",
    "status",
    "attempt",
    "started_at",
    "duration_ms",
    "error_code",
    "error_class",
    "selectors_version",
    "counts",
}


@pytest.fixture
def logger(tmp_path: Path) -> Iterator[logging.Logger]:
    log = configure_logging(RUN_ID, tmp_path / "logs")
    yield log
    close_logging(log)
    logging.captureWarnings(False)


def _path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / f"run_{RUN_ID}.jsonl"


def _file_handlers(log: logging.Logger) -> list[logging.Handler]:
    return [h for h in log.handlers if isinstance(h, logging.FileHandler)]


def _events(tmp_path: Path) -> list[dict[str, object]]:
    lines = _path(tmp_path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _raw(tmp_path: Path) -> str:
    return _path(tmp_path).read_text(encoding="utf-8")


def test_log_contains_masked_id_and_not_full_id(logger: logging.Logger, tmp_path: Path) -> None:
    full_id = "900000001"
    logger.info(
        "row_finished",
        extra={"id_masked": mask_identification(full_id), "row_index": 3},
    )
    logger.info("procesando %s", full_id)
    raw = _raw(tmp_path)
    assert "*****0001" in raw
    assert full_id not in raw


def test_unmasked_id_in_id_masked_is_remasked(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("row_finished", extra={"id_masked": FULL_ID})
    assert _events(tmp_path)[0]["id_masked"] == "******0001"


@pytest.mark.parametrize("value", ["PERSONA FICTICIA UNO", "abc", 123, ["x"], "*" * 3 + "12345"])
def test_id_masked_with_unexpected_content_is_dropped(
    logger: logging.Logger, tmp_path: Path, value: object
) -> None:
    logger.info("row_finished", extra={"id_masked": value})
    event = _events(tmp_path)[0]
    assert "id_masked" not in event
    assert "FICTICIA" not in _raw(tmp_path)


def test_third_party_exception_text_is_not_logged(logger: logging.Logger, tmp_path: Path) -> None:
    try:
        raise RuntimeError(f"fallo con {FULL_ID} en el portal")
    except RuntimeError as exc:
        log_exception(logger, exc, "ERROR_PORTAL")
    raw = _raw(tmp_path)
    event = _events(tmp_path)[0]
    assert FULL_ID not in raw
    assert "fallo con" not in raw
    assert event["error_class"] == "RuntimeError"
    assert event["error_code"] == "ERROR_PORTAL"
    assert event["event"] == "exception"


def test_log_exception_accepts_optional_row_index_and_id_masked(
    logger: logging.Logger, tmp_path: Path
) -> None:
    log_exception(logger, ValueError("x"), "E", row_index=4, id_masked=mask_identification(FULL_ID))
    event = _events(tmp_path)[0]
    assert event["row_index"] == 4
    assert event["id_masked"] == "******0001"


def test_exc_info_is_masked_or_dropped(logger: logging.Logger, tmp_path: Path) -> None:
    try:
        try:
            raise ValueError("causa 1000000002")
        except ValueError as cause:
            raise KeyError(f"contexto {FULL_ID}") from cause
    except KeyError:
        logger.error("falló", exc_info=True, stack_info=True)
    raw = _raw(tmp_path)
    assert FULL_ID not in raw
    assert "1000000002" not in raw
    assert "Traceback" not in raw


def test_filter_drops_exc_info_exc_text_and_stack_info_and_masks_message() -> None:
    try:
        try:
            raise ValueError("causa 1000000002")
        except ValueError as cause:
            raise KeyError(f"contexto {FULL_ID}") from cause
    except KeyError:
        exc_info = sys.exc_info()
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "msg %s", (1000000003,), exc_info)
    record.exc_text = f"texto previo {FULL_ID}"
    record.stack_info = "pila 1.000.000.002"
    assert MaskingFilter().filter(record) is True
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None
    assert record.getMessage() == "msg ******0003"


def test_filter_masks_mapping_args() -> None:
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "valor %(v)s", ({"v": "1.000.000.001"},), None
    )
    MaskingFilter().filter(record)
    assert record.getMessage() == "valor ******0001"


class _BadStr:
    def __str__(self) -> str:
        raise RuntimeError(FULL_ID)


@pytest.mark.parametrize(
    "record_args",
    [("%d", ("texto",)), (_BadStr(), ()), ("%(falta)s", ({"otro": 1},))],
)
def test_filter_survives_failing_get_message(
    record_args: tuple[object, tuple[object, ...]],
) -> None:
    msg, args = record_args
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
    assert MaskingFilter().filter(record) is True
    assert record.getMessage() == ""


def test_failing_get_message_emits_unlisted_event(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info(_BadStr())
    assert _events(tmp_path)[0]["event"] == "unlisted_event"
    assert FULL_ID not in _raw(tmp_path)


def test_note_and_responsible_never_logged(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info(
        "row_finished",
        extra={
            "note": "OBSERVACION LIBRE",
            "responsible": "USR-001",
            "nombre_o_razon_social": "PERSONA FICTICIA UNO",
            "estado_rut": "ACTIVO",
            "identification": FULL_ID,
            "observation": "OTRA NOTA",
            "row_index": 1,
        },
    )
    raw = _raw(tmp_path)
    for forbidden in ("OBSERVACION", "USR-001", "FICTICIA", "ACTIVO", FULL_ID, "OTRA NOTA"):
        assert forbidden not in raw
    assert _events(tmp_path)[0]["row_index"] == 1


def test_only_allowed_fields(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info(
        "row_finished",
        extra={
            "row_index": 2,
            "status": "EXITOSA",
            "source": "FAKE",
            "attempt": 1,
            "duration_ms": 12,
            "error_code": "X",
            "error_class": "Y",
            "selectors_version": "v1.2",
            "started_at": datetime.fromisoformat("2026-10-09T10:15:00-05:00"),
            "counts": {"EXITOSA": 4, "SIN_RESULTADOS": 1},
            "custom_secret": "valor",
        },
    )
    event = _events(tmp_path)[0]
    assert set(event) == ALLOWED_FIELDS - {"id_masked"}
    assert event["counts"] == {"EXITOSA": 4, "SIN_RESULTADOS": 1}
    assert event["selectors_version"] == "v1.2"
    assert event["event"] == "row_finished"


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "source",
        "error_code",
        "error_class",
        "selectors_version",
        "started_at",
        "row_index",
        "attempt",
        "duration_ms",
        "counts",
    ],
)
@pytest.mark.parametrize("bad", [FULL_ID, f"x{FULL_ID}", True, 1.5, float("nan")])
def test_typed_fields_discard_invalid_values(
    logger: logging.Logger, tmp_path: Path, field: str, bad: object
) -> None:
    value = {FULL_ID: 1, "EXITOSA": bad} if field == "counts" else bad
    logger.info("row_finished", extra={field: value})
    event = _events(tmp_path)[0]
    raw = _raw(tmp_path)
    assert FULL_ID not in raw
    assert field not in event or (field == "counts" and event[field] == {})


def test_bool_is_not_a_valid_int(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("row_finished", extra={"row_index": True, "attempt": False})
    event = _events(tmp_path)[0]
    assert "row_index" not in event
    assert "attempt" not in event


def test_naive_started_at_is_discarded(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("run_started", extra={"started_at": datetime(2026, 10, 9, 10, 0)})
    assert "started_at" not in _events(tmp_path)[0]


def test_error_class_with_digit_run_is_discarded(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("row_finished", extra={"error_class": f"Err{FULL_ID}", "error_code": "A1"})
    event = _events(tmp_path)[0]
    assert "error_class" not in event
    assert "error_code" not in event


def test_event_is_closed_catalog(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("mensaje con PERSONA FICTICIA UNO")
    logger.info(RuntimeError(f"texto de tercero {FULL_ID}"))
    logger.info("x", extra={"event": "PERSONA FICTICIA UNO"})
    logger.info("run_finished")
    logger.info("otra cosa", extra={"event": LogEvent.CIRCUIT_OPENED})
    events = [e["event"] for e in _events(tmp_path)]
    assert events == ["unlisted_event"] * 3 + ["run_finished", "circuit_opened"]
    raw = _raw(tmp_path)
    assert "FICTICIA" not in raw
    assert "tercero" not in raw


def test_event_catalog_matches_architecture() -> None:
    assert {e.value for e in LogEvent} == {
        "run_started",
        "row_finished",
        "retry_scheduled",
        "circuit_opened",
        "challenge_detected",
        "challenge_resolved",
        "challenge_timeout",
        "batch_stopped",
        "export_failed",
        "snapshot_saved",
        "purge_executed",
        "run_finished",
        "exception",
        "unlisted_event",
    }


def test_run_id_and_dates_are_not_masked(logger: logging.Logger, tmp_path: Path) -> None:
    started = datetime.fromisoformat("2026-10-09T10:15:00-05:00")
    logger.info("run_started", extra={"started_at": started, "duration_ms": 1234567})
    event = _events(tmp_path)[0]
    assert event["run_id"] == RUN_ID
    assert event["started_at"] == "2026-10-09T10:15:00-05:00"
    assert event["duration_ms"] == 1234567
    ts = datetime.fromisoformat(str(event["ts"]))
    assert ts.utcoffset() is not None
    assert str(event["ts"]).endswith("-05:00")


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "../evil",
        "20261009-101500-ABCD",
        "20261009-101500-abc",
        "x20261009-101500-ab12",
        "20261009-101500-ab12\n",
        "..\\20261009-101500-ab12",
        "\uff12\uff10\uff12\uff16\uff11\uff10\uff10\uff19-101500-ab12",
    ],
)
def test_invalid_run_id_is_rejected(run_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        configure_logging(run_id, tmp_path / "logs")
    assert not (tmp_path / "logs").exists()


def test_creates_directory_and_file_is_utf8_jsonl(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info("run_started")
    logger.info("run_finished")
    assert _path(tmp_path).is_file()
    assert len(_events(tmp_path)) == 2


def test_no_duplicate_handlers_on_second_call(tmp_path: Path) -> None:
    first = configure_logging(RUN_ID, tmp_path / "logs")
    try:
        second = configure_logging(RUN_ID, tmp_path / "logs")
        assert second is first
        assert len(_file_handlers(first)) == 1
        first.info("run_started")
        assert len(_events(tmp_path)) == 1
    finally:
        close_logging(first)
    assert _file_handlers(first) == []


def test_same_run_id_with_other_log_dir_is_rejected(logger: logging.Logger, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="log_dir"):
        configure_logging(RUN_ID, tmp_path / "otro")
    assert not (tmp_path / "otro").exists()


def test_log_does_not_propagate_to_root(logger: logging.Logger) -> None:
    assert logger.propagate is False


def test_child_logger_records_reach_the_file(logger: logging.Logger, tmp_path: Path) -> None:
    child = logging.getLogger(f"{logger.name}.sub")
    child.info("row_finished", extra={"id_masked": mask_identification(FULL_ID)})
    child.info("falla con %s", FULL_ID)
    assert _events(tmp_path)[0]["id_masked"] == "******0001"
    assert FULL_ID not in _raw(tmp_path)


def test_file_can_be_deleted_after_close(tmp_path: Path) -> None:
    log = configure_logging(RUN_ID, tmp_path / "logs")
    log.info("run_started")
    close_logging(log)
    _path(tmp_path).unlink()
    assert not _path(tmp_path).exists()


def test_package_logger_and_warnings_do_not_reach_stderr(
    logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = _file_handlers(logger)[0]
    assert isinstance(handler, logging.FileHandler)
    # pytest restaura showwarning en cada fase: se reinstala la captura en la prueba.
    logging.captureWarnings(False)
    configure_logging(RUN_ID, Path(handler.baseFilename).parent)  # idempotente
    package_logger = logging.getLogger("rut_checker")
    assert package_logger.propagate is False
    assert any(isinstance(h, logging.NullHandler) for h in package_logger.handlers)
    assert sum(isinstance(h, logging.NullHandler) for h in package_logger.handlers) == 1
    logging.getLogger("rut_checker.adapters").error("fallo %s", FULL_ID)
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn(FULL_ID, UserWarning, stacklevel=1)
    warnings.showwarning(FULL_ID, UserWarning, "f.py", 1)
    captured = capsys.readouterr()
    assert FULL_ID not in captured.err
    assert FULL_ID not in captured.out
    warnings_logger = logging.getLogger("py.warnings")
    assert warnings_logger.propagate is False
    assert any(isinstance(h, logging.NullHandler) for h in warnings_logger.handlers)


@pytest.mark.parametrize("code", ["", "a", "ERROR1", "X" * 41, "ERROR PORTAL", FULL_ID])
def test_log_exception_rejects_invalid_error_code(
    logger: logging.Logger, tmp_path: Path, code: str
) -> None:
    with pytest.raises(ValueError, match="error_code"):
        log_exception(logger, RuntimeError("x"), code)
    assert not _path(tmp_path).read_text(encoding="utf-8")


def test_started_at_is_normalized_to_bogota(logger: logging.Logger, tmp_path: Path) -> None:
    logger.info(
        "run_started", extra={"started_at": datetime.fromisoformat("2026-10-09T15:15:00+00:00")}
    )
    assert _events(tmp_path)[0]["started_at"] == "2026-10-09T10:15:00-05:00"


def _capturing_warnings() -> bool:
    return getattr(warnings.showwarning, "__module__", "") == "logging"


def test_close_logging_restores_warnings_when_last_run(tmp_path: Path) -> None:
    logging.captureWarnings(False)
    first = configure_logging(RUN_ID, tmp_path / "logs")
    second = configure_logging("20261009-101501-cd34", tmp_path / "logs")
    assert _capturing_warnings()
    close_logging(first)
    assert _capturing_warnings()
    close_logging(second)
    assert not _capturing_warnings()
