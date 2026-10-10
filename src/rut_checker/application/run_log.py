"""Registro técnico de una ejecución desde `application` (ARQUITECTURA §10).

`application` no puede importar `infra` (prueba de arquitectura), así que no usa `LogEvent` ni
`log_exception`; este módulo emite los mismos eventos con sus nombres literales sobre el
`logging.Logger` inyectado (solo `infra/logging.py` crea loggers). Una prueba comprueba que
`EVENT_NAMES` sea un subconjunto del catálogo cerrado `LogEvent`.

Garantías: solo campos de la lista blanca (`row_index`, `id_masked`, `source`, `status`,
`attempt`, `duration_ms`, `error_code`, `error_class`, `started_at`, `counts`). Nunca nombre,
`estado_rut`, nota, responsable ni texto de excepción: de una excepción solo sale su clase.
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Final

from rut_checker.domain.models import RutResult
from rut_checker.domain.status import QueryStatus, SourceKind

RUN_STARTED: Final = "run_started"
ROW_FINISHED: Final = "row_finished"
RETRY_SCHEDULED: Final = "retry_scheduled"
CIRCUIT_OPENED: Final = "circuit_opened"
BATCH_STOPPED: Final = "batch_stopped"
RUN_FINISHED: Final = "run_finished"
EXCEPTION: Final = "exception"
EVENT_NAMES: Final = (
    RUN_STARTED,
    ROW_FINISHED,
    RETRY_SCHEDULED,
    CIRCUIT_OPENED,
    BATCH_STOPPED,
    RUN_FINISHED,
    EXCEPTION,
)


class RunLog:
    """Fachada tipada sobre el logger de la ejecución."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def run_started(self, source: SourceKind, started_at: datetime) -> None:
        """Inicio del lote: fuente primaria e instante de inicio."""
        self._logger.info(
            RUN_STARTED, extra={"event": RUN_STARTED, "source": source, "started_at": started_at}
        )

    def row_finished(
        self,
        row_index: int,
        id_masked: str | None,
        result: RutResult,
        duration_ms: int,
        attempt: int,
    ) -> None:
        """Fin de una fila; `attempt` es 0 si no se consultó ninguna fuente."""
        self._logger.info(
            ROW_FINISHED,
            extra={
                "event": ROW_FINISHED,
                "row_index": row_index,
                "id_masked": id_masked,
                "source": result.source,
                "status": result.status,
                "duration_ms": duration_ms,
                "attempt": attempt,
            },
        )

    def retry_scheduled(self, row_index: int, id_masked: str | None, attempt: int) -> None:
        """Se reintentará la fila tras el intento `attempt` (que acaba de fallar)."""
        self._logger.info(
            RETRY_SCHEDULED,
            extra={
                "event": RETRY_SCHEDULED,
                "row_index": row_index,
                "id_masked": id_masked,
                "attempt": attempt,
            },
        )

    def circuit_opened(self, row_index: int, reason_code: str) -> None:
        """Se abrió el circuito en la fila indicada; `reason_code` es un `StopReason`."""
        self._logger.warning(
            CIRCUIT_OPENED,
            extra={"event": CIRCUIT_OPENED, "row_index": row_index, "error_code": reason_code},
        )

    def batch_stopped(self, row_index: int, reason_code: str) -> None:
        """El lote se detuvo en la fila indicada; `reason_code` es un `StopReason`."""
        self._logger.warning(
            BATCH_STOPPED,
            extra={"event": BATCH_STOPPED, "row_index": row_index, "error_code": reason_code},
        )

    def error(
        self,
        error: BaseException,
        code: str,
        row_index: int | None = None,
        id_masked: str | None = None,
    ) -> None:
        """Registra una excepción solo con su clase y un código (`[A-Z_]{1,40}`)."""
        extra: dict[str, object] = {
            "event": EXCEPTION,
            "error_code": code,
            "error_class": type(error).__name__,
            "row_index": row_index,
            "id_masked": id_masked,
        }
        self._logger.error(EXCEPTION, extra=extra)

    def run_finished(self, counts: Mapping[QueryStatus, int]) -> None:
        """Fin del lote con el conteo por estado."""
        self._logger.info(RUN_FINISHED, extra={"event": RUN_FINISHED, "counts": dict(counts)})
