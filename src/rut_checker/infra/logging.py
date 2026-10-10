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
- `purge_counts` (evento `purge_executed`): solo claves `<carpeta>.<tipo>`, `deleted` y `failed`
  de un conjunto cerrado (`purge_keys.COUNT_KEYS`) con enteros; no admite texto libre.
- Los campos estructurados (`ts`, `started_at`, `run_id`, contadores) no pasan por el enmascarado.
- `configure_logging` silencia `rut_checker` y `py.warnings` (NullHandler, sin propagación).
- `silence_unconfigured_loggers` (CLI) pone un `NullHandler` en el root: un logger de terceros
  sin configurar (Playwright, asyncio) no cae en `logging.lastResort` ni escribe a stderr.
"""

import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from rut_checker.domain.status import ChallengeEvent, SourceKind
from rut_checker.infra.log_format import (
    ERROR_CODE,
    JsonlFormatter,
    LogEvent,
    MaskingFilter,
    trace_sites_of,
)

__all__ = [
    "ChallengeLogSink",
    "JsonlFormatter",
    "LogEvent",
    "MaskingFilter",
    "close_logging",
    "close_run_logging",
    "configure_logging",
    "log_exception",
    "log_export_failed",
    "log_purge_executed",
    "silence_unconfigured_loggers",
]

_RUN_ID_PATTERN: Final = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", re.ASCII)
_LOGGER_PREFIX: Final = "rut_checker.run."
_PACKAGE_LOGGER: Final = "rut_checker"
_WARNINGS_LOGGER: Final = "py.warnings"


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


def silence_unconfigured_loggers() -> None:
    """Evita que los loggers sin configurar escriban a stderr (`logging.lastResort`).

    Añade un `NullHandler` al logger raíz (una sola vez). Se hace con un handler y no con
    `lastResort = None` porque, sin handlers, Python escribiría en stderr el aviso "No handlers
    could be found for logger ...". Los loggers con handlers propios (el de la ejecución) no
    cambian. Lo llama la CLI al arrancar.
    """
    root = logging.getLogger()
    if not any(isinstance(h, logging.NullHandler) for h in root.handlers):
        root.addHandler(logging.NullHandler())


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
    with_trace: bool = False,
) -> None:
    """Registra una excepción solo con su clase y un código; nunca `str`/`repr`/mensajes.

    Args:
        logger: Logger de la ejecución.
        exc: Excepción (solo se usa `type(exc).__name__`).
        error_code: Código de error (`[A-Z_]{1,40}`).
        row_index: Fila afectada, si aplica.
        id_masked: Identificación ya enmascarada con `mask_identification`, si aplica.
        with_trace: Añade los últimos sitios `archivo:línea:función` del traceback (solo el nombre
            del archivo, sin mensajes ni código fuente) para poder diagnosticar un fallo inesperado.
    """
    if ERROR_CODE.fullmatch(error_code) is None:
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
    if with_trace:
        extra["error_trace"] = trace_sites_of(exc)
    logger.error(LogEvent.EXCEPTION.value, extra=extra)


def log_export_failed(logger: logging.Logger, error_code: str, error_class: str) -> None:
    """Registra el evento `export_failed` (ERROR_EXPORTACION o respaldo JSON) sin detalles."""
    if ERROR_CODE.fullmatch(error_code) is None:
        raise ValueError("error_code inválido (se espera [A-Z_]{1,40})")
    logger.error(
        LogEvent.EXPORT_FAILED.value,
        extra={
            "event": LogEvent.EXPORT_FAILED,
            "error_code": error_code,
            "error_class": error_class,
        },
    )


def log_purge_executed(
    logger: logging.Logger, purge_counts: Mapping[str, int], source: SourceKind | None = None
) -> None:
    """Registra `purge_executed` con conteos por `<carpeta>.<tipo>` (claves cerradas) y totales.

    Los conteos con claves fuera de `purge_keys.COUNT_KEYS` se descartan; nunca se registran
    rutas ni nombres de archivo.
    """
    logger.info(
        LogEvent.PURGE_EXECUTED.value,
        extra={
            "event": LogEvent.PURGE_EXECUTED,
            "purge_counts": dict(purge_counts),
            "source": source,
        },
    )


class ChallengeLogSink:
    """Recolector de eventos de desafío que los escribe en el log de la ejecución.

    El adaptador del portal se crea antes que el logger, así que el sumidero se enlaza después
    (`bind`). Solo emite el evento cerrado y `duration_ms`: nunca identificación ni texto libre.
    El adaptador desconoce la fila en curso; el evento precede al `row_finished` de su fila.
    """

    def __init__(self) -> None:
        self._logger: logging.Logger | None = None

    def bind(self, logger: logging.Logger) -> None:
        """Enlaza el logger de la ejecución."""
        self._logger = logger

    def __call__(self, event: ChallengeEvent, duration_ms: int) -> None:
        if self._logger is None:
            return
        name = LogEvent(event.value)
        level = logging.WARNING if event is ChallengeEvent.TIMEOUT else logging.INFO
        self._logger.log(level, name.value, extra={"event": name, "duration_ms": duration_ms})


def close_run_logging(run_id: str) -> None:
    """Cierra el logger de la ejecución `run_id` (no hace nada si no estaba configurado).

    Permite a quien solo conoce el `run_id` (la CLI) liberar el archivo sin llamar a
    `logging.getLogger`.

    Raises:
        ValueError: Si `run_id` no tiene el formato esperado.
    """
    if _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("run_id con formato inválido (se espera AAAAMMDD-HHMMSS-<4 hex>)")
    close_logging(logging.getLogger(f"{_LOGGER_PREFIX}{run_id}"))
