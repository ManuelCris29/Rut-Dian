"""Regla de vigencia de la copia del RUT aportada por el tercero (RN-07, G9-G10)."""

from datetime import date
from enum import StrEnum

from rut_checker.domain.models import CopyEvidence

MAX_COPY_AGE_DAYS = 30


class CopyVerdict(StrEnum):
    """Veredicto sobre la copia; la fuente documental lo traduce a un estado de consulta.

    `VALID` -> `VALIDADA_COPIA_RUT`; `EXPIRED` -> `PENDIENTE_VALIDACION_MANUAL` ("copia vencida");
    `FUTURE_DATE` -> `PENDIENTE_VALIDACION_MANUAL` ("fecha de copia inválida"). La decisión
    la toma `DocumentCopySource` (ADR-0002, specs/excepciones.md).
    """

    VALID = "VALID"
    EXPIRED = "EXPIRED"
    FUTURE_DATE = "FUTURE_DATE"


def evaluate_copy_evidence(evidence: CopyEvidence, today: date) -> CopyVerdict:
    """Evalúa la antigüedad de la copia del RUT frente a `MAX_COPY_AGE_DAYS`.

    `today` lo calcula quien llama en la zona `America/Bogota`
    (`datetime.now(ZoneInfo("America/Bogota")).date()`, vía `Clock`); el dominio no lee el reloj.
    Con exactamente 30 días la copia sigue vigente; con 31 está vencida; una fecha posterior a
    `today` devuelve `FUTURE_DATE` (no lanza).
    """
    age_days = (today - evidence.copy_date).days
    if age_days < 0:
        return CopyVerdict.FUTURE_DATE
    return CopyVerdict.VALID if age_days <= MAX_COPY_AGE_DAYS else CopyVerdict.EXPIRED
