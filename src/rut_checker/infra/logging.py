"""Logging JSONL con enmascarado de datos personales (ARQUITECTURA §10, RNF-01).

Un archivo por ejecución: `<log_dir>/run_<run_id>.jsonl`, UTF-8, un evento JSON por línea.

Garantías:
- Lista blanca de campos con tipos cerrados; lo que no cumple el tipo se descarta
  (`status` ∈ QueryStatus, `source` ∈ SourceKind, `counts` con claves QueryStatus y enteros).
  Todo lo demás en `extra` (`note`, `responsible`, `identification`, nombre, `estado_rut`)
  se descarta.
- `event` pertenece a un catálogo cerrado (`LogEvent`); el texto del mensaje nunca se copia.
- `MaskingFilter` enmascara el mensaje y elimina `exc_info`, `exc_text` y `stack_info`
  sin renderizarlos.
- El formateador nunca emite tracebacks ni `str(exc)`; de una excepción solo salen
  `error_code` y `error_class` (ver `log_exception`).
- `id_masked` debe llegar ya enmascarado con `mask_identification`; si llega un número sin
  enmascarar se enmascara de nuevo, y cualquier otro contenido se descarta.
- Los campos estructurados (`ts`, `started_at`, `run_id`, contadores) no pasan por el enmascarado.
- `configure_logging` silencia `rut_checker` y `py.warnings` (NullHandler, sin propagación).
"""

import json
import logging
import os
import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from rut_checker.domain.masking import mask_digit_runs, mask_identification
from rut_checker.domain.status import QueryStatus, SourceKind

_RUN_ID_PATTERN: Final = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", re.ASCII)
_ERROR_CODE: Final = re.compile(r"[A-Z_]{1,40}", re.ASCII)
_ERROR_CLASS: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}", re.ASCII)
_SELECTORS_VERSION: Final = re.compile(r"v?[0-9]{1,4}(\.[0-9]{1,4}){0,3}", re.ASCII)
_MASKED_ID: Final = re.compile(r"\*+[0-9]{0,4}", re.ASCII)
_DIGITS_ID: Final = re.compile(r"[0-9][0-9.,/ -]*", re.ASCII)
_TIMEZONE: Final = ZoneInfo("America/Bogota")
_LOGGER_PREFIX: Final = "rut_checker.run."
_PACKAGE_LOGGER: Final = "rut_checker"
_WARNINGS_LOGGER: Final = "py.warnings"
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


def _optional_fields(record: logging.LogRecord) -> dict[str, object]:
    """Campos opcionales permitidos, validados por tipo; lo que no cumple se descarta."""
    fields: dict[str, object] = {
        "id_masked": _masked_id(getattr(record, "id_masked", None)),
        "source": _enum_value(SourceKind, getattr(record, "source", None)),
        "status": _enum_value(QueryStatus, getattr(record, "status", None)),
        "error_code": _pattern_value(_ERROR_CODE, getattr(record, "error_code", None)),
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
    raw_counts = getattr(record, "counts", None)
    if isinstance(raw_counts, dict):
        fields["counts"] = _counts(raw_counts)
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


class _RunFileHandler(logging.FileHandler):
    """Handler propio, identificable para evitar duplicados y cerrarlo con limpieza."""


def _own_handlers(logger: logging.Logger) -> list[_RunFileHandler]:
    return [h for h in logger.handlers if isinstance(h, _RunFileHandler)]


def _silence_outside_run() -> None:
    """Evita salidas fuera del archivo de la ejecución (stderr por `lastResort`, advertencias).

    El logger `rut_checker` y `py.warnings` reciben un `NullHandler` y no propagan, de modo que
    un `logger.error(...)` de cualquier módulo del paquete o un `warnings.warn(...)` que lleve
    un id no llega a la consola. Es idempotente.
    """
    for name in (_PACKAGE_LOGGER, _WARNINGS_LOGGER):
        outer = logging.getLogger(name)
        if not any(isinstance(h, logging.NullHandler) for h in outer.handlers):
            outer.addHandler(logging.NullHandler())
        outer.propagate = False
    logging.captureWarnings(True)


def configure_logging(run_id: str, log_dir: Path) -> logging.Logger:
    """Configura el logger de una ejecución y devuelve el logger listo para usar.

    Es idempotente por `run_id`. Activa `logging.captureWarnings(True)`: las advertencias de
    todo el proceso (`warnings.warn`) dejan de ir a stderr y se descartan (`py.warnings` sin
    salida). `close_logging` lo revierte al cerrar el último run activo.
    Los demás módulos reciben este logger (solo este módulo llama a `logging.getLogger`).

    Args:
        run_id: Identificador con formato `AAAAMMDD-HHMMSS-<4 hex>`; se valida para que
            no pueda usarse como vector de ruta.
        log_dir: Directorio de logs; se crea si no existe.

    Raises:
        ValueError: Si `run_id` no tiene el formato esperado, o si ya está configurado
            con otro `log_dir`.
    """
    if _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("run_id con formato inválido (se espera AAAAMMDD-HHMMSS-<4 hex>)")
    _silence_outside_run()
    logger = logging.getLogger(f"{_LOGGER_PREFIX}{run_id}")
    target = log_dir / f"run_{run_id}.jsonl"
    existing = _own_handlers(logger)
    if existing:
        if any(h.baseFilename != os.path.abspath(target) for h in existing):
            raise ValueError("run_id ya configurado con otro log_dir")
        return logger
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = _RunFileHandler(target, encoding="utf-8")
    handler.addFilter(MaskingFilter())
    handler.setFormatter(JsonlFormatter(run_id))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def _any_active_run() -> bool:
    manager = logging.Logger.manager
    return any(
        isinstance(candidate, logging.Logger) and _own_handlers(candidate)
        for name, candidate in list(manager.loggerDict.items())
        if name.startswith(_LOGGER_PREFIX)
    )


def close_logging(logger: logging.Logger) -> None:
    """Cierra y retira los handlers del logger (libera el archivo en Windows).

    Si ya no queda ningún run activo, desactiva `captureWarnings` (las advertencias vuelven
    al comportamiento normal del proceso).
    """
    for handler in _own_handlers(logger):
        handler.close()
        logger.removeHandler(handler)
    if not _any_active_run():
        logging.captureWarnings(False)


def log_exception(
    logger: logging.Logger,
    exc: BaseException,
    error_code: str,
    *,
    row_index: int | None = None,
    id_masked: str | None = None,
) -> None:
    """Registra una excepción solo con su clase y un código; nunca `str`/`repr`/traceback.

    Args:
        logger: Logger de la ejecución.
        exc: Excepción (solo se usa `type(exc).__name__`).
        error_code: Código de error (`[A-Z_]{1,40}`).
        row_index: Fila afectada, si aplica.
        id_masked: Identificación ya enmascarada con `mask_identification`, si aplica.
    """
    if _ERROR_CODE.fullmatch(error_code) is None:
        raise ValueError("error_code inválido (se espera [A-Z_]{1,40})")
    extra: dict[str, object] = {
        "event": LogEvent.EXCEPTION,
        "error_code": error_code,
        "error_class": type(exc).__name__,
    }
    if row_index is not None:
        extra["row_index"] = row_index
    if id_masked is not None:
        extra["id_masked"] = id_masked
    logger.error(LogEvent.EXCEPTION.value, extra=extra)
