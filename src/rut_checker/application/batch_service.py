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
- Reintentos: `RetryPolicy` inyectable (por defecto `NoRetry`) con salvaguardas propias del
  servicio (`bounded_retry_delay`): errores que nunca se reintentan, tope `MAX_ATTEMPTS` y
  retrasos no finitos o negativos descartados. El ritmo lo aplica `Pacer`.
- El respaldo debe ser local: se rechaza un `fallback` con `paced=True` o del portal.
- `operator` queda inyectado para T-45 (bloqueos). `run` es de un solo uso y cierra `primary`
  y `fallback` al terminar (`finally`).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from rut_checker.application.clock import Sleeper
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
from rut_checker.domain.models import (
    CopyEvidence,
    IdentificationInput,
    InputRow,
    QueryOutcome,
    RutResult,
)
from rut_checker.domain.status import SourceKind
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort

UNEXPECTED_LOG_CODE = "UNEXPECTED"

type _DedupeKey = tuple[str, CopyEvidence | None, str | None]


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
    cache: dict[_DedupeKey, RutResult] = field(default_factory=dict)
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
            operator: Canal con el operador (lo usará T-45 para bloqueos).
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
        state = _RunState(Pacer(self._sleeper, self._settings.min_delay_between_queries_s))
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
        key = self._dedupe_key(ident)
        cached = state.cache.get(key)
        if cached is not None:
            return self._finish(row, ident, cached, started, 0)
        if state.stop_reason is None:
            result, attempt = self._query_primary(row, ident, state)
        else:
            result, attempt = self._query_fallback(row, ident, state), 1
        state.cache[key] = result
        return self._finish(row, ident, result, started, attempt)

    def _dedupe_key(self, ident: IdentificationInput) -> _DedupeKey:
        """Con fuente externa (`paced`) solo cuenta la identificación: copia y nota no cambian
        lo que devuelve el portal y cada consulta extra pesa sobre la DIAN (RF-11, RNF-02).
        Con fuentes locales cuenta también la evidencia y la nota (espacios normalizados)."""
        if self._primary.paced:
            return (ident.identification, None, None)
        note = " ".join(ident.note.split()) if ident.note else None
        return (ident.identification, ident.copy_evidence, note)

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
                return self._primary.query(ident), attempt
            except RutCheckerError as error:
                delay = bounded_retry_delay(self._retry_policy, error, attempt)
                if delay is None:
                    return self._failed(error, row, ident, state), attempt
                self._log.retry_scheduled(row.row_index, masked_id(row, ident), attempt)
                attempt += 1
                retry_delay = delay
            except Exception as error:  # parada segura ante cualquier error no previsto
                return self._unexpected(error, row, ident, state), attempt

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
        if translation.stop is not None:
            self._stop(translation.stop, row, state)
        return result_for(translation, self._primary.kind)

    def _unexpected(
        self, error: Exception, row: InputRow, ident: IdentificationInput, state: _RunState
    ) -> RutResult:
        """Parada segura: registra solo la clase; la fila se trata como `StructureChanged`."""
        self._log.error(error, UNEXPECTED_LOG_CODE, row.row_index, masked_id(row, ident))
        self._stop(UNEXPECTED.stop or StopReason.UNEXPECTED_ERROR, row, state)
        return result_for(UNEXPECTED, self._primary.kind)

    def _stop(self, reason: StopReason, row: InputRow, state: _RunState) -> None:
        state.stop_reason = reason
        self._log.batch_stopped(row.row_index, reason.value)

    def _close_sources(self) -> None:
        for source in (self._primary, self._fallback):
            try:
                source.close()
            except Exception as error:  # cerrar uno no debe impedir cerrar el otro
                self._log.error(error, "CLOSE_FAILED")
