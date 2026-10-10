"""`BatchQueryService`: validación, dedupe, delegación en la fuente y manejo de errores.

Decisiones (ARQUITECTURA §5.3, §7 y §8; T-35):
- La traducción excepción -> `QueryStatus` vive solo en `application/translation.py`
  (`translate`); todo camino de error del servicio pasa por ella.
- Cada fila termina en exactamente un estado y el informe conserva el orden de entrada (G7).
- Dedupe: con fuente local la clave es `(identificación normalizada, evidencia de copia, nota
  con espacios colapsados)`; con `primary.paced` (fuente externa) es solo la identificación,
  porque copia y nota no cambian lo que devuelve el portal (RF-11, RNF-02). Filas con la misma
  clave comparten una sola consulta y el mismo `RutResult` (con su propia fila,
  `IdentificationInput` y `duration_ms = 0`); cada fila conserva su evidencia y su nota.
- Fila inválida -> `ENTRADA_INVALIDA` con fuente `SIN_CONSULTA`, sin consultar. Fila con
  `possible_glued_check_digit` -> `PENDIENTE_VALIDACION_MANUAL` ("posible NIT con DV pegado")
  con fuente `CONTINGENCIA_MANUAL`, sin consultar, tenga o no copia vigente.
- `fuente` de una fila consultada es `RutResult.source`. Si la consulta falló (excepción
  traducida) es el canal intentado, `primary.kind`; si ese canal es la fuente documental,
  `CONTINGENCIA_MANUAL`.
- Excepción inesperada (no de dominio, o de dominio sin traducción como `ExportError`): se
  registra solo clase y código `UNEXPECTED`, la fila se trata como `StructureChanged`
  (`ESTRUCTURA_CAMBIADA`), el lote se detiene y las filas restantes pasan por `fallback`.
  Nunca se registra ni se guarda el texto de la excepción.
- Reintentos: `RetryPolicy` inyectable (por defecto `NoRetry`; la real es `BackoffRetryPolicy`)
  con salvaguardas propias del servicio (`bounded_retry_delay`). El ritmo lo aplica `Pacer`,
  también antes de la primera llamada de cada ejecución.
- Paradas y circuito (T-45, `circuit.py`): `PortalUnavailable` agotado abre el circuito y esa fila
  va al respaldo; 3 `QueryTimeout` seguidos lo abren; 3 `SessionExpired`/`IncompleteResult` seguidos
  lo abren (`REPEATED_SESSION_FAILURES`); 2 bloqueos seguidos detienen el lote y el
  1.º pregunta al operador (sin identificación en el mensaje). Si la política lanza una
  excepción, el informe es parcial (parada `UNEXPECTED_ERROR`); si lo hace el operador, cuenta
  como que declina (`OPERATOR_DECLINED`, se registra `OPERATOR_FAILED`). `KeyboardInterrupt`
  se propaga tras cerrar las fuentes (`finally`): el operador cancela, no se devuelve informe.
- El respaldo debe ser local: se rechaza un `fallback` con `paced=True` o del portal. `run` es de
  un solo uso y cierra `primary` y `fallback` al terminar (`finally`).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from rut_checker.application.circuit import CIRCUIT_REASONS, Streaks
from rut_checker.application.clock import Sleeper
from rut_checker.application.dedupe import DedupeCache
from rut_checker.application.pacing import Pacer
from rut_checker.application.report import BatchReport, StopReason
from rut_checker.application.retry_policy import NoRetry, RetryPolicy, bounded_retry_delay
from rut_checker.application.row_input import build_identification
from rut_checker.application.row_results import (
    GLUED_REASON,
    masked_id,
    pending_result,
    with_stop_note,
)
from rut_checker.application.run_log import RunLog
from rut_checker.application.translation import UNEXPECTED, result_for, translate
from rut_checker.domain.errors import InvalidIdentification, RutCheckerError
from rut_checker.domain.models import IdentificationInput, InputRow, QueryOutcome, RutResult
from rut_checker.domain.status import SourceKind
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort

UNEXPECTED_LOG_CODE = "UNEXPECTED"
OPERATOR_LOG_CODE = "OPERATOR_FAILED"


class BatchSettings(Protocol):
    """Parte de `infra.Settings` que usa el servicio (`application` no importa `infra`)."""

    @property
    def min_delay_between_queries_s(self) -> float:
        """Pausa mínima entre consultas a una fuente con `paced=True` (RNF-02)."""
        ...


@dataclass(slots=True)
class _RunState:
    """Estado mutable de una ejecución."""

    pacer: Pacer
    cache: DedupeCache
    streaks: Streaks = field(default_factory=Streaks)
    stop_reason: StopReason | None = None


class BatchQueryService:
    """Procesa un lote de filas contra una fuente primaria con respaldo."""

    def __init__(
        self,
        primary: RutSourcePort,
        fallback: RutSourcePort,
        operator: OperatorPort,
        clock: Clock,
        sleeper: Sleeper,
        settings: BatchSettings,
        logger: logging.Logger,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """Crea el servicio.

        Args:
            primary: Fuente principal (portal, copia del RUT, contingencia o pruebas).
            fallback: Fuente local para las filas posteriores a una parada del lote.
            operator: Canal con el operador (pregunta al 1.º bloqueo seguido).
            clock: Reloj (`America/Bogota`) para `queried_at` y duraciones.
            sleeper: Espera inyectable (ritmo y backoff).
            settings: Configuración de ritmo.
            logger: Logger de la ejecución, creado por `infra.logging.configure_logging`.
            retry_policy: Política de reintentos; por defecto no se reintenta.

        Raises:
            ValueError: Si `fallback` consulta un sistema externo (`paced`) o es el portal.
        """
        if fallback.paced or fallback.kind is SourceKind.PORTAL_DIAN_C1:
            raise ValueError("el respaldo debe ser una fuente local, no el portal")
        self._primary = primary
        self._fallback = fallback
        self._operator = operator
        self._clock = clock
        self._sleeper = sleeper
        self._settings = settings
        self._log = RunLog(logger)
        self._retry_policy = retry_policy or NoRetry()
        self._consumed = False

    def run(self, rows: list[InputRow]) -> BatchReport:
        """Procesa todas las filas, en orden, y devuelve un desenlace por fila.

        Raises:
            RuntimeError: Si el servicio ya se ejecutó (cierra las fuentes al terminar).
        """
        if self._consumed:
            raise RuntimeError("BatchQueryService es de un solo uso")
        self._consumed = True
        self._log.run_started(self._primary.kind, self._clock.now())
        state = _RunState(
            Pacer(self._sleeper, self._settings.min_delay_between_queries_s),
            DedupeCache(self._primary.paced),
        )
        try:
            outcomes = tuple(self._process_row(row, state) for row in rows)
        finally:
            self._close_sources()
        report = BatchReport(outcomes, state.stop_reason)
        self._log.run_finished(report.counts)
        return report

    # --- una fila -----------------------------------------------------------------------

    def _process_row(self, row: InputRow, state: _RunState) -> QueryOutcome:
        started = self._clock.now()
        try:
            ident = build_identification(row)
        except InvalidIdentification as error:
            return self._finish(row, None, self._invalid_result(error), started, 0)
        if ident.possible_glued_check_digit:
            return self._finish(row, ident, pending_result(GLUED_REASON), started, 0)
        stopped = state.stop_reason is not None
        cached = state.cache.lookup(ident, stopped=stopped)
        if cached is not None:
            return self._finish(row, ident, cached, started, 0)
        if not stopped:
            result, attempt = self._query_primary(row, ident, state)
            # `PortalUnavailable` agotado detiene el lote y resuelve esta fila con el respaldo
            by_fallback = state.stop_reason is StopReason.PORTAL_UNAVAILABLE
        else:
            result, attempt, by_fallback = self._query_fallback(row, ident, state), 1, True
        state.cache.store(ident, result, by_fallback=by_fallback)
        return self._finish(row, ident, result, started, attempt)

    def _invalid_result(self, error: InvalidIdentification) -> RutResult:
        return result_for(translate(error), self._primary.kind)

    def _finish(
        self,
        row: InputRow,
        ident: IdentificationInput | None,
        result: RutResult,
        started: datetime,
        attempt: int,
    ) -> QueryOutcome:
        duration_ms = int((self._clock.now() - started).total_seconds() * 1000)
        outcome = QueryOutcome(
            row=row,
            identification=ident,
            result=result,
            queried_at=started,
            duration_ms=max(duration_ms, 0),
        )
        self._log.row_finished(
            row.row_index, masked_id(row, ident), result, outcome.duration_ms, attempt
        )
        return outcome

    # --- consulta a las fuentes ----------------------------------------------------------

    def _query_primary(
        self, row: InputRow, ident: IdentificationInput, state: _RunState
    ) -> tuple[RutResult, int]:
        attempt = 1
        retry_delay = 0.0
        while True:
            state.pacer.before_call(self._primary.paced, retry_delay)
            try:
                result = self._primary.query(ident)
            except RutCheckerError as error:
                failure = error
            except Exception as error:  # parada segura ante cualquier error no previsto
                return self._unexpected(error, row, ident, state), attempt
            else:
                state.streaks.observe_result(result.status)
                return result, attempt
            try:
                delay = bounded_retry_delay(self._retry_policy, failure, attempt)
            except Exception as error:  # una política rota no debe perder el lote
                return self._unexpected(error, row, ident, state), attempt
            if delay is None:
                return self._failed(failure, row, ident, state), attempt
            self._log.retry_scheduled(row.row_index, masked_id(row, ident), attempt)
            attempt += 1
            retry_delay = delay

    def _query_fallback(
        self, row: InputRow, ident: IdentificationInput, state: _RunState
    ) -> RutResult:
        try:
            result = self._fallback.query(ident)
        except Exception as error:  # el respaldo nunca debe romper el lote
            self._log.error(error, "FALLBACK_FAILED", row.row_index, masked_id(row, ident))
            result = pending_result("error en la fuente de respaldo")
        return with_stop_note(result, state.stop_reason)

    # --- errores ------------------------------------------------------------------------

    def _failed(
        self, error: RutCheckerError, row: InputRow, ident: IdentificationInput, state: _RunState
    ) -> RutResult:
        translation = translate(error)
        if translation.unexpected:
            return self._unexpected(error, row, ident, state)
        verdict = state.streaks.on_failure(error)
        stop = translation.stop or verdict.stop
        if stop is None and verdict.ask_operator:
            stop = self._ask_operator(row, ident)
        if stop is None:
            return result_for(translation, self._primary.kind)
        self._stop(stop, row, state)
        if verdict.row_to_fallback:
            return self._query_fallback(row, ident, state)
        return result_for(translation, self._primary.kind)

    def _ask_operator(self, row: InputRow, ident: IdentificationInput) -> StopReason | None:
        """Primer bloqueo seguido: `None` si el operador continúa, o el motivo de parada."""
        message = (
            f"Verificación de seguridad no resuelta en la fila {row.row_index + 1}. "
            "¿Continuar con el lote?"
        )
        try:
            if self._operator.confirm_continue(message):
                return None
        except Exception as error:  # sin respuesta equivale a que no (ADR-0003 §4)
            self._log.error(error, OPERATOR_LOG_CODE, row.row_index, masked_id(row, ident))
            return StopReason.OPERATOR_DECLINED
        return StopReason.OPERATOR_DECLINED

    def _unexpected(
        self, error: Exception, row: InputRow, ident: IdentificationInput, state: _RunState
    ) -> RutResult:
        """Parada segura: registra solo la clase; la fila se trata como `StructureChanged`."""
        self._log.error(error, UNEXPECTED_LOG_CODE, row.row_index, masked_id(row, ident))
        self._stop(UNEXPECTED.stop or StopReason.UNEXPECTED_ERROR, row, state)
        return result_for(UNEXPECTED, self._primary.kind)

    def _stop(self, reason: StopReason, row: InputRow, state: _RunState) -> None:
        state.stop_reason = reason
        if reason in CIRCUIT_REASONS:
            self._log.circuit_opened(row.row_index, reason.value)
        self._log.batch_stopped(row.row_index, reason.value)

    def _close_sources(self) -> None:
        for source in (self._primary, self._fallback):
            try:
                source.close()
            except Exception as error:  # cerrar uno no debe impedir cerrar el otro
                self._log.error(error, "CLOSE_FAILED")
