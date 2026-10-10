"""Formato del log JSONL: catálogo de eventos, lista blanca de campos y enmascarado (T-43).

Separado de `infra/logging.py` (configuración de handlers y API de registro). Este módulo no
crea loggers: solo valida y serializa. Garantías en `infra/logging.py` (ARQUITECTURA §10).
"""

import json
import logging
import re
import traceback
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from rut_checker.domain.masking import mask_digit_runs, mask_identification
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.infra.purge_keys import COUNT_KEYS

ERROR_CODE: Final = re.compile(r"[A-Z_]{1,40}", re.ASCII)
_ERROR_CLASS: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}", re.ASCII)
_SELECTORS_VERSION: Final = re.compile(r"v?[0-9]{1,4}(\.[0-9]{1,4}){0,3}", re.ASCII)
_TRACE_SITE: Final = re.compile(
    r"[A-Za-z0-9_.-]{1,64}:[0-9]{1,6}:[A-Za-z_<][A-Za-z0-9_<>]{0,63}", re.ASCII
)
_MAX_TRACE_SITES: Final = 8
_MASKED_ID: Final = re.compile(r"\*+[0-9]{0,4}", re.ASCII)
_DIGITS_ID: Final = re.compile(r"[0-9][0-9.,/ -]*", re.ASCII)
_TIMEZONE: Final = ZoneInfo("America/Bogota")
_INT_FIELDS: Final = ("row_index", "attempt", "duration_ms")


class LogEvent(StrEnum):
    """Catálogo cerrado de eventos (ARQUITECTURA §10); lo demás se registra como `UNLISTED`."""

    RUN_STARTED = "run_started"
    ROW_FINISHED = "row_finished"
    RETRY_SCHEDULED = "retry_scheduled"
    CIRCUIT_OPENED = "circuit_opened"
    CHALLENGE_DETECTED = "challenge_detected"
    CHALLENGE_RESOLVED = "challenge_resolved"
    CHALLENGE_TIMEOUT = "challenge_timeout"
    BATCH_STOPPED = "batch_stopped"
    EXPORT_FAILED = "export_failed"
    SNAPSHOT_SAVED = "snapshot_saved"
    PURGE_EXECUTED = "purge_executed"
    RUN_FINISHED = "run_finished"
    EXCEPTION = "exception"
    UNLISTED = "unlisted_event"


def _enum_value[E: StrEnum](enum_type: type[E], value: object) -> str | None:
    """Valor del miembro del enum si `value` es exactamente uno de ellos; si no, `None`."""
    if not isinstance(value, str):
        return None
    try:
        return enum_type(value).value
    except ValueError:
        return None


def _pattern_value(pattern: re.Pattern[str], value: object) -> str | None:
    """`value` si es texto que cumple el patrón completo y no contiene números largos."""
    if isinstance(value, str) and pattern.fullmatch(value) and mask_digit_runs(value) == value:
        return value
    return None


def _plain_int(value: object) -> int | None:
    """Entero estricto (excluye `bool`)."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _safe_message(record: logging.LogRecord) -> str:
    """Mensaje formateado; vacío si el formateo falla (no se filtra texto ajeno)."""
    try:
        return record.getMessage()
    except Exception:
        return ""


def _event_name(record: logging.LogRecord) -> str:
    declared = getattr(record, "event", None)
    candidate = declared if declared is not None else _safe_message(record)
    return _enum_value(LogEvent, candidate) or LogEvent.UNLISTED.value


def _masked_id(value: object) -> str | None:
    """`id_masked` ya enmascarado; un número sin enmascarar se enmascara; lo demás se descarta."""
    if not isinstance(value, str):
        return None
    if _MASKED_ID.fullmatch(value):
        return value
    if _DIGITS_ID.fullmatch(value):
        return mask_identification(value)
    return None


def _trace_sites(value: object) -> list[str]:
    """Sitios `archivo:línea:función` válidos (hasta 8); lo demás se descarta."""
    if not isinstance(value, list):
        return []
    sites = [_pattern_value(_TRACE_SITE, item) for item in value]
    return [site for site in sites if site is not None][:_MAX_TRACE_SITES]


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        status = _enum_value(QueryStatus, key)
        number = _plain_int(count)
        if status is not None and number is not None:
            result[status] = number
    return result


def _purge_counts(value: object) -> dict[str, int]:
    """Conteos de purga: solo claves del conjunto cerrado `COUNT_KEYS` y enteros estrictos."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        number = _plain_int(count)
        if isinstance(key, str) and key in COUNT_KEYS and number is not None:
            result[key] = number
    return result


def _optional_fields(record: logging.LogRecord) -> dict[str, object]:
    """Campos opcionales permitidos, validados por tipo; lo que no cumple se descarta."""
    fields: dict[str, object] = {
        "id_masked": _masked_id(getattr(record, "id_masked", None)),
        "source": _enum_value(SourceKind, getattr(record, "source", None)),
        "status": _enum_value(QueryStatus, getattr(record, "status", None)),
        "error_code": _pattern_value(ERROR_CODE, getattr(record, "error_code", None)),
        "error_class": _pattern_value(_ERROR_CLASS, getattr(record, "error_class", None)),
        "selectors_version": _pattern_value(
            _SELECTORS_VERSION, getattr(record, "selectors_version", None)
        ),
    }
    for name in _INT_FIELDS:
        fields[name] = _plain_int(getattr(record, name, None))
    started_at = getattr(record, "started_at", None)
    if isinstance(started_at, datetime) and started_at.utcoffset() is not None:
        fields["started_at"] = started_at.astimezone(_TIMEZONE).isoformat()
    trace = _trace_sites(getattr(record, "error_trace", None))
    if trace:
        fields["error_trace"] = trace
    raw_counts = getattr(record, "counts", None)
    if isinstance(raw_counts, dict):
        fields["counts"] = _counts(raw_counts)
    purge_counts = _purge_counts(getattr(record, "purge_counts", None))
    if purge_counts:
        fields["purge_counts"] = purge_counts
    return {key: value for key, value in fields.items() if value is not None}


class MaskingFilter(logging.Filter):
    """Enmascara en el registro cualquier secuencia que parezca una identificación.

    Formatea el mensaje con sus argumentos, enmascara el resultado y deja `args` vacío;
    así también se cubren argumentos no textuales (enteros) y mapeos. Si el formateo
    falla, el mensaje queda vacío. `exc_info`, `exc_text` y `stack_info` se eliminan sin
    renderizar el traceback (ni la excepción ni sus `__cause__`/`__context__` llegan al log).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_digit_runs(_safe_message(record))
        record.args = None
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class JsonlFormatter(logging.Formatter):
    """Formateador JSON de una línea que emite solo campos permitidos y tipados."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        """Serializa el registro; ignora `exc_info`, `exc_text` y `stack_info`."""
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, _TIMEZONE).isoformat(
                timespec="milliseconds"
            ),
            "event": _event_name(record),
            "run_id": self._run_id,
            **_optional_fields(record),
        }
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def trace_sites_of(exc: BaseException) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)[-_MAX_TRACE_SITES:]
    return [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames]
