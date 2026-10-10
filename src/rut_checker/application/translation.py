"""Traducción excepción de dominio -> `QueryStatus` (ARQUITECTURA §7): único lugar del sistema."""

from dataclasses import dataclass

from rut_checker.application.report import StopReason
from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
    IncompleteResult,
    InvalidIdentification,
    PortalUnavailable,
    QueryTimeout,
    RutCheckerError,
    SessionExpired,
    StructureChanged,
)
from rut_checker.domain.models import RutResult
from rut_checker.domain.status import QueryStatus, SourceKind


@dataclass(frozen=True, slots=True)
class Translation:
    """Estado, mensaje genérico y, si aplica, motivo de parada del lote."""

    status: QueryStatus
    observation: str
    stop: StopReason | None = None
    unexpected: bool = False


# Error sin traducción: se trata como `StructureChanged` (parada segura, ARQUITECTURA §7).
UNEXPECTED = Translation(
    QueryStatus.ESTRUCTURA_CAMBIADA, str(StructureChanged()), StopReason.UNEXPECTED_ERROR, True
)


def translate(error: RutCheckerError) -> Translation:
    """Excepción de dominio -> estado. Sin traducción devuelve `UNEXPECTED`."""
    match error:
        case InvalidIdentification():
            return Translation(QueryStatus.ENTRADA_INVALIDA, str(error))
        case PortalUnavailable():
            return Translation(QueryStatus.PORTAL_NO_DISPONIBLE, str(error))
        case QueryTimeout():
            return Translation(QueryStatus.TIEMPO_AGOTADO, str(error))
        case SessionExpired():
            return Translation(QueryStatus.SESION_VENCIDA, str(error))
        case IncompleteResult():
            return Translation(QueryStatus.RESULTADO_INCOMPLETO, str(error))
        case HumanInterventionRequired() | AccessBlocked():
            return Translation(QueryStatus.REQUIERE_INTERVENCION_HUMANA, str(error))
        case StructureChanged():
            return Translation(
                QueryStatus.ESTRUCTURA_CAMBIADA, str(error), StopReason.STRUCTURE_CHANGED
            )
        case _:
            return UNEXPECTED


def result_for(translation: Translation, channel: SourceKind) -> RutResult:
    """`RutResult` de una fila con error traducido.

    `ENTRADA_INVALIDA` -> `SIN_CONSULTA`. Si no, la fuente es el canal intentado; si ese canal
    es la fuente documental, `CONTINGENCIA_MANUAL`, para no sugerir una validación documental
    que no ocurrió.
    """
    if translation.status is QueryStatus.ENTRADA_INVALIDA:
        source = SourceKind.SIN_CONSULTA
    elif channel is SourceKind.COPIA_RUT_TERCERO:
        source = SourceKind.CONTINGENCIA_MANUAL
    else:
        source = channel
    return RutResult(status=translation.status, source=source, observation=translation.observation)
