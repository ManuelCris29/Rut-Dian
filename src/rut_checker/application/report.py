"""Informe de una ejecución del lote (sin datos personales fuera de los `QueryOutcome`)."""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from rut_checker.domain.models import QueryOutcome
from rut_checker.domain.status import QueryStatus


class StopReason(StrEnum):
    """Motivo cerrado por el que el servicio detuvo el lote (nunca texto libre)."""

    STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


@dataclass(frozen=True, slots=True)
class BatchReport:
    """Resultado de `BatchQueryService.run`.

    Attributes:
        outcomes: Un `QueryOutcome` por fila de entrada, en el orden original (G7).
        stop_reason: Motivo de parada, o `None` si el lote se procesó completo. Las filas
            posteriores a la parada se resolvieron con la fuente de respaldo.
    """

    outcomes: tuple[QueryOutcome, ...]
    stop_reason: StopReason | None = None

    @property
    def counts(self) -> dict[QueryStatus, int]:
        """Filas por estado (solo los estados presentes)."""
        return dict(Counter(outcome.result.status for outcome in self.outcomes))

    @property
    def stopped(self) -> bool:
        """`True` si el lote se detuvo antes de consultar todas las filas con la fuente primaria."""
        return self.stop_reason is not None
