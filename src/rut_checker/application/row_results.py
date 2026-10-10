"""Resultados y utilidades de fila que usa `BatchQueryService` (sin traducción de errores)."""

import re

from rut_checker.application.report import StopReason
from rut_checker.domain.masking import mask_identification
from rut_checker.domain.models import IdentificationInput, InputRow, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind

_ASCII_DIGITS = re.compile(r"[0-9]+")
PENDING_PREFIX = "Pendiente de validación manual"
GLUED_REASON = "posible NIT con DV pegado"
_STOP_NOTES = {
    StopReason.STRUCTURE_CHANGED: "Lote detenido: el portal cambió",
    StopReason.UNEXPECTED_ERROR: "Lote detenido por un error inesperado",
}


def pending_result(reason: str) -> RutResult:
    return RutResult(
        status=QueryStatus.PENDIENTE_VALIDACION_MANUAL,
        source=SourceKind.CONTINGENCIA_MANUAL,
        observation=f"{PENDING_PREFIX}: {reason}",
    )


def with_stop_note(result: RutResult, stop: StopReason | None) -> RutResult:
    """Añade el motivo de la parada a las filas pendientes; las validadas quedan intactas."""
    if stop is None or result.status is not QueryStatus.PENDIENTE_VALIDACION_MANUAL:
        return result
    return RutResult(
        status=result.status,
        source=result.source,
        observation=f"{result.observation}; {_STOP_NOTES[stop]}",
    )


def masked_id(row: InputRow, ident: IdentificationInput | None) -> str | None:
    """Identificación enmascarada para el log.

    En una fila inválida el valor crudo solo se enmascara si es puramente numérico; si trae
    letras, separadores o decimales podría ser texto libre y se reemplaza por `*`.
    """
    if ident is not None:
        return mask_identification(ident.identification)
    raw = row.raw_identification
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    text = str(raw)
    return mask_identification(text) if _ASCII_DIGITS.fullmatch(text) else "*"
