"""Fuente de contingencia (ADR-0002 §2, RF-12): deja la fila pendiente de validación manual.

No consulta ningún sistema externo (`paced = False`), no lee archivos y no devuelve datos
personales: `estado_rut` y `name` quedan vacíos.
"""

from rut_checker.domain.models import IdentificationInput, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind

PENDING_OBSERVATION = "Pendiente de validación manual"


def pending_manual_result(reason: str | None = None) -> RutResult:
    """Resultado `PENDIENTE_VALIDACION_MANUAL` con fuente `CONTINGENCIA_MANUAL`.

    Args:
        reason: Motivo opcional (texto sin identificaciones) que se añade a la observación.
    """
    observation = PENDING_OBSERVATION if reason is None else f"{PENDING_OBSERVATION}: {reason}"
    return RutResult(
        status=QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        source=SourceKind.CONTINGENCIA_MANUAL,
        observation=observation,
    )


class ContingencySource:
    """Implementación de `RutSourcePort` que siempre exige validación manual."""

    @property
    def kind(self) -> SourceKind:
        """Origen del dato: `CONTINGENCIA_MANUAL`."""
        return SourceKind.CONTINGENCIA_MANUAL

    @property
    def paced(self) -> bool:
        """No consulta un sistema externo: no aplica ritmo."""
        return False

    def query(self, ident: IdentificationInput) -> RutResult:
        """Devuelve siempre pendiente de validación manual (ignora la entrada)."""
        return pending_manual_result()

    def close(self) -> None:
        """Sin recursos que liberar; idempotente."""
