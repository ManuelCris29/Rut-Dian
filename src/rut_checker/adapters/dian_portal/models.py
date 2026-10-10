"""Modelos Pydantic de `config/selectors.yaml` (T-37).

Inmutables, estrictos (sin coerción de tipos), sin claves extra y sin eco del valor en los
errores de validación.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(max_length=500)]
Strategy = Literal["label", "role", "text", "css", "testid"]


class _Strict(BaseModel):
    """Base inmutable, sin claves extra, sin coerción de tipos y sin eco del valor en errores."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class SelectorSpec(_Strict):
    """Un localizador: por rol/etiqueta/texto antes que CSS (skill playwright-rpa)."""

    strategy: Strategy
    value: Text = ""
    role: Text = ""
    name: Text = ""
    required: bool = True

    @model_validator(mode="after")
    def _complete_for_strategy(self) -> Self:
        needed = self.role if self.strategy == "role" else self.value
        if not needed.strip():
            raise ValueError("selector incompleto para su estrategia")
        return self


class FormSelectors(_Strict):
    """Elementos del formulario de consulta."""

    id_input: SelectorSpec
    submit_button: SelectorSpec


class ResultSelectors(_Strict):
    """Elementos del resultado; `name` es opcional (SPEC §5 solo exige el estado)."""

    status: SelectorSpec
    name: SelectorSpec | None = None
    no_result_msg: SelectorSpec


class DetectionSelectors(_Strict):
    """Marcadores de detección (ADR-0003 §2). Vacío solo con `*_observed: none` y evidencia."""

    maintenance_url_markers: list[Text] = Field(default_factory=list, max_length=20)
    challenge_markers: list[SelectorSpec] = Field(default_factory=list, max_length=20)
    challenge_observed: Literal["none"] | None = None
    challenge_evidence: Text = ""
    block_markers: list[SelectorSpec] = Field(default_factory=list, max_length=20)
    block_observed: Literal["none"] | None = None
    block_evidence: Text = ""

    @model_validator(mode="after")
    def _observed_none_excludes_markers(self) -> Self:
        if (self.challenge_observed and self.challenge_markers) or (
            self.block_observed and self.block_markers
        ):
            raise ValueError("`*_observed: none` es contradictorio con marcadores presentes")
        return self


class PortalSelectors(_Strict):
    """Contenido validado de `selectors.yaml`."""

    synthetic: bool = False
    validated: bool
    version: Text
    approval_ref: Text
    source_snapshot: Text
    form: FormSelectors
    result: ResultSelectors
    detection: DetectionSelectors
