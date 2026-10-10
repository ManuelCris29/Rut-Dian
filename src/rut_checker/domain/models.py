"""Modelos de dominio inmutables: fila cruda, entrada, evidencia de copia, resultado y desenlace.

Reglas de protección de datos (Ley 1581 de 2012):
- `repr`/`str` enmascaran la identificación con `mask_identification`.
- `note` (observación), `responsible`, `name`, `observation` y los valores crudos de `InputRow`
  (salvo la identificación enmascarada) nunca aparecen en `repr`/`str` (Obs-8).
- `hide_input_in_errors` evita que un `ValidationError` de pydantic copie valores de entrada
  (p. ej. la identificación) en su mensaje.
- Los errores de formato se lanzan como `InvalidIdentification` (conjunto cerrado de motivos,
  sin valor crudo); al no ser `ValueError`, pydantic los propaga sin envolverlos.
"""

import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from rut_checker.domain.errors import IncompleteResult, InvalidIdentification, InvalidReason
from rut_checker.domain.masking import mask_identification
from rut_checker.domain.status import QueryStatus, SourceKind

MAX_NOTE_LENGTH = 200
_RESPONSIBLE_CODE = re.compile(r"[A-Za-z0-9._-]{2,40}")
_DIGITS = re.compile(r"[0-9]+")
_SINGLE_DIGIT = re.compile(r"[0-9]")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SOURCES_WITH_PERSONAL_FIELDS = frozenset({SourceKind.PORTAL_DIAN_C1, SourceKind.FAKE})


class _DomainModel(BaseModel):
    """Base de los modelos de dominio: inmutables y sin valores de entrada en los errores.

    No usar `model_copy(update=...)` con estos modelos: no revalida, así que podría
    saltarse los invariantes. Construir una instancia nueva.
    """

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)


class CopyEvidence(_DomainModel):
    """Evidencia documental: copia del RUT aportada por el tercero (RN-07, opción C).

    Attributes:
        copy_date: Fecha de emisión de la copia. Acepta `date` o texto ISO `AAAA-MM-DD`;
            cualquier otro tipo (int/timestamp, `datetime`, bool) o texto es ilegible.
        responsible: Código o usuario de quien validó (`^[A-Za-z0-9._-]{2,40}$`), nunca un
            nombre completo (Obs-8). No se muestra en `repr`.
    """

    copy_date: date
    responsible: str = Field(repr=False)

    @field_validator("copy_date", mode="before")
    @classmethod
    def _copy_date_is_strict(cls, value: object) -> date:
        if isinstance(value, datetime):
            raise InvalidIdentification(InvalidReason.UNREADABLE_COPY_DATE)
        if isinstance(value, date):
            return value
        if isinstance(value, str) and _ISO_DATE.fullmatch(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise InvalidIdentification(InvalidReason.UNREADABLE_COPY_DATE) from None
        raise InvalidIdentification(InvalidReason.UNREADABLE_COPY_DATE)

    @field_validator("responsible", mode="before")
    @classmethod
    def _responsible_is_code(cls, value: object) -> str:
        if not isinstance(value, str) or _RESPONSIBLE_CODE.fullmatch(value) is None:
            raise InvalidIdentification(InvalidReason.INVALID_RESPONSIBLE)
        return value


class IdentificationInput(_DomainModel):
    """Una fila de entrada ya normalizada y válida en formato.

    Contrato: `identification` llega **solo con dígitos** y sin DV (el DV va en `dv`);
    la normalización (`1000000001.0`, `900.000.001-7`, espacios) y las reglas de longitud o de
    dígito de verificación son de `domain/validators.py` (T-41), no de este modelo.
    Una fila que no cumpla esto no se representa aquí sino con `InputRow` + `ENTRADA_INVALIDA`.

    Attributes:
        identification: Número normalizado (solo dígitos). Se enmascara en `repr`.
        dv: Dígito de verificación opcional (un dígito). Un `dv` mal formado se reporta como
            `BAD_CHECK_DIGIT` ("DV incorrecto"): un DV que no es un dígito es, por definición,
            incorrecto.
        copy_evidence: Copia del RUT aportada, si la hay.
        note: Observación libre del área (máx. 200 caracteres). Nunca se muestra en `repr`.
        possible_glued_check_digit: Lo calcula `validate_identification`: 10 dígitos, prefijo 8 o 9,
            sin DV y con el último dígito igual al DV de los 9 primeros. Indica posible NIT con
            DV pegado; el servicio la envía a revisión manual sin consultar la fuente.
    """

    identification: str
    dv: str | None = None
    copy_evidence: CopyEvidence | None = None
    note: str | None = Field(default=None, repr=False)
    possible_glued_check_digit: bool = Field(default=False, repr=False)

    @field_validator("identification", mode="before")
    @classmethod
    def _identification_is_digits(cls, value: object) -> str:
        if not isinstance(value, str):
            raise InvalidIdentification(InvalidReason.NON_NUMERIC)
        if not value:
            raise InvalidIdentification(InvalidReason.EMPTY)
        if _DIGITS.fullmatch(value) is None:
            raise InvalidIdentification(InvalidReason.NON_NUMERIC)
        return value

    @field_validator("dv", mode="before")
    @classmethod
    def _dv_is_single_digit(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or _SINGLE_DIGIT.fullmatch(value) is None:
            raise InvalidIdentification(InvalidReason.BAD_CHECK_DIGIT)
        return value

    @field_validator("note", mode="before")
    @classmethod
    def _note_is_short(cls, value: object) -> str | None:
        if value is None:
            return None
        # Se reutiliza OBSERVATION_TOO_LONG para una observación no textual: evita ampliar
        # el conjunto cerrado de motivos por un caso que ningún lector produce.
        if not isinstance(value, str) or len(value) > MAX_NOTE_LENGTH:
            raise InvalidIdentification(InvalidReason.OBSERVATION_TOO_LONG)
        return value

    def __repr_args__(self) -> Iterable[tuple[str | None, object]]:
        for name, value in super().__repr_args__():
            if name == "identification" and isinstance(value, str):
                yield name, mask_identification(value)
            else:
                yield name, value


def _numeric_text(value: str | int | float) -> str:
    """Texto de un valor crudo; un float entero se muestra sin `.0` (se enmascara igual)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class InputRow(_DomainModel):
    """Fila de entrada tal como la leyó `io/readers` (valores crudos, sin validar).

    `raw_identification` conserva el tipo de la celda (texto, `int` o `float`) para que el
    dominio decida: convertir `1.001` a texto lo confundiría con miles. Las demás columnas son
    texto.

    Existe para poder representar filas inválidas (`ENTRADA_INVALIDA`) en el desenlace sin
    construir un `IdentificationInput`. Solo `raw_identification` se muestra en `repr`, y
    enmascarada; el resto de los valores crudos se oculta.
    """

    row_index: int = Field(ge=0)
    raw_identification: str | int | float | None = None
    raw_dv: str | None = Field(default=None, repr=False)
    raw_copy_date: str | None = Field(default=None, repr=False)
    raw_responsible: str | None = Field(default=None, repr=False)
    raw_note: str | None = Field(default=None, repr=False)

    def __repr_args__(self) -> Iterable[tuple[str | None, object]]:
        for name, value in super().__repr_args__():
            if name == "raw_identification" and isinstance(value, str | int | float):
                yield name, mask_identification(_numeric_text(value))
            else:
                yield name, value


class RutResult(_DomainModel):
    """Resultado de una fuente para una identificación.

    Los invariantes de combinación estado/fuente/datos son errores de programación y lanzan
    `ValueError` (pydantic: `ValidationError`):
    - `VALIDADA_COPIA_RUT` exige fuente `COPIA_RUT_TERCERO` y `estado_rut`/`name` vacíos (D-1, D-3).
    - `ENTRADA_INVALIDA` exige fuente `SIN_CONSULTA`.
    - `estado_rut` y `name` no vacíos solo con fuente `PORTAL_DIAN_C1` o `FAKE`.

    `EXITOSA` sin `estado_rut` es un dato incompleto del canal, no un error de programación:
    lanza `IncompleteResult` (ARQUITECTURA §7).

    Attributes:
        status: Estado final de la consulta.
        source: Origen del dato (columna `fuente`).
        estado_rut: Estado tal cual lo muestra el portal; vacío si no aplica; no se muestra
            en `repr` (ARQUITECTURA §10).
        name: Nombre o razón social (solo portal); no se muestra en `repr`.
        observation: Mensaje para la columna `observacion`; no se muestra en `repr`.
    """

    status: QueryStatus
    source: SourceKind
    estado_rut: str = Field(default="", repr=False)
    name: str = Field(default="", repr=False)
    observation: str = Field(default="", repr=False)

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        has_personal = bool(self.estado_rut or self.name)
        if self.status is QueryStatus.VALIDADA_COPIA_RUT and (
            self.source is not SourceKind.COPIA_RUT_TERCERO or has_personal
        ):
            raise ValueError("VALIDADA_COPIA_RUT exige fuente de copia y sin estado ni nombre")
        if (
            self.status is QueryStatus.ENTRADA_INVALIDA
            and self.source is not SourceKind.SIN_CONSULTA
        ):
            raise ValueError("ENTRADA_INVALIDA exige fuente SIN_CONSULTA")
        if has_personal and self.source not in _SOURCES_WITH_PERSONAL_FIELDS:
            raise ValueError(
                "estado_rut y nombre solo provienen del portal o de la fuente de pruebas"
            )
        if (
            self.source is SourceKind.SIN_CONSULTA
            and self.status is not QueryStatus.ENTRADA_INVALIDA
        ):
            raise ValueError("la fuente SIN_CONSULTA exige el estado ENTRADA_INVALIDA")
        if self.status is QueryStatus.EXITOSA:
            if self.source not in _SOURCES_WITH_PERSONAL_FIELDS:
                raise ValueError("EXITOSA solo proviene del portal o de la fuente de pruebas")
            if not self.estado_rut.strip():
                raise IncompleteResult
        return self


class QueryOutcome(_DomainModel):
    """Desenlace de una fila: fila cruda, entrada validada (si la hay), resultado y tiempos.

    `identification` es `None` solo para filas `ENTRADA_INVALIDA` (no se pudo construir una
    entrada válida). El inverso se permite: una fila `ENTRADA_INVALIDA` puede conservar su
    `IdentificationInput` (p. ej. DV incorrecto detectado por T-41 tras normalizar).
    La columna `dv` de la salida sale únicamente de la entrada
    (`identification.dv`, o `row.raw_dv` si la fila es inválida): ninguna fuente la aporta.

    Attributes:
        row: Fila tal como se leyó (identificación enmascarada en `repr`).
        identification: Entrada validada, o `None` si la fila es inválida.
        result: Resultado de la fuente.
        queried_at: Instante de procesamiento, con zona horaria. La zona `America/Bogota`
            la fija quien llama con el `Clock` (T-35); este modelo solo exige que no sea ingenuo.
        duration_ms: Duración de la consulta en milisegundos.
    """

    row: InputRow
    identification: IdentificationInput | None
    result: RutResult
    queried_at: AwareDatetime
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _missing_identification_means_invalid_input(self) -> Self:
        if self.identification is None and self.result.status is not QueryStatus.ENTRADA_INVALIDA:
            raise ValueError("sin entrada validada el estado debe ser ENTRADA_INVALIDA")
        return self
