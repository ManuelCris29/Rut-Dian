"""De la fila cruda (`InputRow`) a la entrada validada (`IdentificationInput`)."""

from rut_checker.domain.errors import InvalidIdentification, InvalidReason
from rut_checker.domain.models import CopyEvidence, IdentificationInput, InputRow
from rut_checker.domain.validators import validate_identification


def build_identification(row: InputRow) -> IdentificationInput:
    """Valida la fila y arma la entrada con su evidencia de copia y su nota.

    La evidencia solo existe si hay `raw_copy_date`; en ese caso el responsable es obligatorio.
    Un responsable sin fecha de copia es una fila inválida (motivo cerrado).

    Raises:
        InvalidIdentification: Identificación, DV, fecha de copia, responsable o nota inválidos
            (con un motivo cerrado, sin el valor crudo).
    """
    base = validate_identification(row.raw_identification, row.raw_dv)
    return IdentificationInput(
        identification=base.identification,
        dv=base.dv,
        copy_evidence=_copy_evidence(row),
        note=_blank_to_none(row.raw_note),
        possible_glued_check_digit=base.possible_glued_check_digit,
    )


def _blank_to_none(value: str | None) -> str | None:
    return value if value is not None and value.strip() else None


def _copy_evidence(row: InputRow) -> CopyEvidence | None:
    copy_date = _blank_to_none(row.raw_copy_date)
    if copy_date is None:
        if _blank_to_none(row.raw_responsible) is not None:
            raise InvalidIdentification(InvalidReason.RESPONSIBLE_WITHOUT_COPY_DATE)
        return None
    return CopyEvidence(
        copy_date=copy_date.strip(), responsible=(row.raw_responsible or "").strip()
    )
