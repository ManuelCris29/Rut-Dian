"""Rachas de fallos y circuito abierto (ARQUITECTURA §7; ADR-0003 §4; excepciones.md).

Cuenta solo consultas reales a la fuente primaria (las filas resueltas por dedupe no cuentan).
Decisiones documentadas:
- Bloqueo = `HumanInterventionRequired` o `AccessBlocked` (ADR-0003 §4 los trata igual).
- `SessionExpired` e `IncompleteResult` comparten una racha de 3 (O-1): un portal que no
  entrega sesión o resultado completo tres veces seguidas no se sigue consultando.
- Los contadores de bloqueos, tiempos agotados y fallos de sesión se reinician únicamente con
  `EXITOSA` o `SIN_RESULTADOS` (excepciones.md); un fallo de otra clase no reinicia ninguno, lo que
  es la lectura conservadora (se insiste menos contra el portal).
- Las constantes no son configurables: son reglas de cumplimiento (RNF-02).
"""

from dataclasses import dataclass
from typing import Final

from rut_checker.application.report import StopReason
from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
    IncompleteResult,
    PortalUnavailable,
    QueryTimeout,
    RutCheckerError,
    SessionExpired,
)
from rut_checker.domain.status import QueryStatus

BLOCKS_TO_STOP: Final = 2
TIMEOUTS_TO_OPEN: Final = 3
SESSION_FAILURES_TO_OPEN: Final = 3
CIRCUIT_REASONS: Final = frozenset(
    {
        StopReason.PORTAL_UNAVAILABLE,
        StopReason.REPEATED_TIMEOUTS,
        StopReason.REPEATED_SESSION_FAILURES,
    }
)
_RESETTING: Final = frozenset({QueryStatus.EXITOSA, QueryStatus.SIN_RESULTADOS})


@dataclass(frozen=True, slots=True)
class Verdict:
    """Reacción del servicio ante un fallo definitivo de una fila.

    Attributes:
        stop: Motivo de parada del lote, si lo hay.
        ask_operator: Primer bloqueo: preguntar al operador si se continúa.
        row_to_fallback: La propia fila (portal caído tras reintentos) se resuelve con el respaldo.
    """

    stop: StopReason | None = None
    ask_operator: bool = False
    row_to_fallback: bool = False


class Streaks:
    """Contadores de bloqueos, tiempos agotados y fallos de sesión seguidos de una ejecución."""

    def __init__(self) -> None:
        self._blocks = 0
        self._timeouts = 0
        self._session_failures = 0

    def observe_result(self, status: QueryStatus) -> None:
        """Una consulta devolvió resultado: `EXITOSA` o `SIN_RESULTADOS` reinician las rachas."""
        if status in _RESETTING:
            self._blocks = 0
            self._timeouts = 0
            self._session_failures = 0

    def on_failure(self, error: RutCheckerError) -> Verdict:
        """Registra un fallo definitivo (tras sus reintentos) y decide la reacción."""
        if isinstance(error, PortalUnavailable):
            return Verdict(stop=StopReason.PORTAL_UNAVAILABLE, row_to_fallback=True)
        if isinstance(error, QueryTimeout):
            self._timeouts += 1
            if self._timeouts >= TIMEOUTS_TO_OPEN:
                return Verdict(stop=StopReason.REPEATED_TIMEOUTS)
        if isinstance(error, SessionExpired | IncompleteResult):
            self._session_failures += 1
            if self._session_failures >= SESSION_FAILURES_TO_OPEN:
                return Verdict(stop=StopReason.REPEATED_SESSION_FAILURES)
        if isinstance(error, HumanInterventionRequired | AccessBlocked):
            self._blocks += 1
            if self._blocks >= BLOCKS_TO_STOP:
                return Verdict(stop=StopReason.REPEATED_BLOCKS)
            return Verdict(ask_operator=True)
        return Verdict()
