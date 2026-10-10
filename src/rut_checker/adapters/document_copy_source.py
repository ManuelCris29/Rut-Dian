"""Fuente documental (ADR-0002 §2, RN-07, opción C): valida contra la copia del RUT aportada.

Decisiones:
- Nunca lee la copia (PDF ni archivo alguno): solo usa la fecha y el responsable que el área
  registró. Por eso `estado_rut` y `name` quedan siempre vacíos (D-3).
- `kind = COPIA_RUT_TERCERO` identifica al adaptador; la columna `fuente` sale siempre de
  `RutResult.source`. `paced` sigue al fallback (normalmente `ContingencySource`, sin ritmo).
- Copia vigente (<= 30 días): `VALIDADA_COPIA_RUT` con fuente `COPIA_RUT_TERCERO`.
- Copia vencida o con fecha futura: la fila queda `PENDIENTE_VALIDACION_MANUAL` con fuente
  `CONTINGENCIA_MANUAL`, porque no se validó nada contra la copia; marcarla como
  `COPIA_RUT_TERCERO` sugeriría una validación documental que no ocurrió. No se invoca el fallback.
- Sin evidencia: delega en el `fallback` (el resultado lo produce él).
- Observación compuesta: parte fija (<= ~120 caracteres con responsable de hasta 40) + nota del
  área (<= 200, validada en el modelo), con espacios colapsados y secuencias numéricas largas
  enmascaradas (`mask_digit_runs`); la nota se conserva también en vencida/futura: <= ~330.
  Nunca incluye la identificación completa.
"""

from datetime import date
from typing import assert_never

from rut_checker.adapters.contingency_source import pending_manual_result
from rut_checker.domain.evidence import CopyVerdict, evaluate_copy_evidence
from rut_checker.domain.masking import mask_digit_runs
from rut_checker.domain.models import CopyEvidence, IdentificationInput, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind
from rut_checker.ports.clock import Clock
from rut_checker.ports.rut_source import RutSourcePort


class DocumentCopySource:
    """Implementación de `RutSourcePort` basada en la evidencia de copia del RUT."""

    def __init__(self, fallback: RutSourcePort, clock: Clock) -> None:
        """Crea la fuente.

        Args:
            fallback: Fuente a la que se delega cuando la fila no trae copia.
            clock: Reloj que da la fecha de referencia en `America/Bogota`.
        """
        self._fallback = fallback
        self._clock = clock

    @property
    def kind(self) -> SourceKind:
        """Origen del dato: `COPIA_RUT_TERCERO`."""
        return SourceKind.COPIA_RUT_TERCERO

    @property
    def paced(self) -> bool:
        """Sigue al fallback (normalmente `ContingencySource`: sin ritmo)."""
        return self._fallback.paced

    def query(self, ident: IdentificationInput) -> RutResult:
        """Evalúa la copia aportada o delega en el fallback si no hay evidencia."""
        evidence = ident.copy_evidence
        if evidence is None:
            return self._fallback.query(ident)
        verdict = evaluate_copy_evidence(evidence, self._clock.today())
        match verdict:
            case CopyVerdict.VALID:
                return _validated(evidence, ident.note)
            case CopyVerdict.EXPIRED:
                reason = f"copia vencida ({evidence.copy_date.isoformat()})"
                return _pending(reason, ident.note)
            case CopyVerdict.FUTURE_DATE:
                return _pending("fecha de copia inválida", ident.note)
            case _ as unreachable:
                assert_never(unreachable)

    def close(self) -> None:
        """Cierra el fallback (idempotente si este lo es)."""
        self._fallback.close()


def _with_area_note(observation: str, note: str | None) -> str:
    """Añade la nota del área: espacios colapsados y secuencias numéricas enmascaradas."""
    clean = mask_digit_runs(" ".join(note.split())) if note else ""
    return f"{observation}. Observación del área: {clean}" if clean else observation


def _pending(reason: str, note: str | None) -> RutResult:
    base = pending_manual_result(reason)
    return RutResult(
        status=base.status,
        source=base.source,
        observation=_with_area_note(base.observation, note),
    )


def _validated(evidence: CopyEvidence, note: str | None) -> RutResult:
    observation = _validated_observation(evidence.copy_date, evidence.responsible)
    return RutResult(
        status=QueryStatus.VALIDADA_COPIA_RUT,
        source=SourceKind.COPIA_RUT_TERCERO,
        observation=_with_area_note(observation, note),
    )


def _validated_observation(copy_date: date, responsible: str) -> str:
    return (
        f"Validado contra copia del RUT de fecha {copy_date.isoformat()}; "
        f"responsable: {responsible}"
    )
