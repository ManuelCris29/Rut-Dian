"""Modelos Pydantic de `config/selectors.yaml` (T-37).

Inmutables, estrictos (sin coerción de tipos), sin claves extra y sin eco del valor en los
errores de validación.
"""

import re
import unicodedata
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(max_length=500)]
Strategy = Literal["label", "role", "text", "css", "testid"]


# Roles ARIA admitidos por `get_by_role` de Playwright (error de configuración al cargar).
ARIA_ROLES = frozenset(
    {
        "alert",
        "alertdialog",
        "application",
        "article",
        "banner",
        "blockquote",
        "button",
        "caption",
        "cell",
        "checkbox",
        "code",
        "columnheader",
        "combobox",
        "complementary",
        "contentinfo",
        "definition",
        "deletion",
        "dialog",
        "directory",
        "document",
        "emphasis",
        "feed",
        "figure",
        "form",
        "generic",
        "grid",
        "gridcell",
        "group",
        "heading",
        "img",
        "insertion",
        "link",
        "list",
        "listbox",
        "listitem",
        "log",
        "main",
        "marquee",
        "math",
        "menu",
        "menubar",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "meter",
        "navigation",
        "none",
        "note",
        "option",
        "paragraph",
        "presentation",
        "progressbar",
        "radio",
        "radiogroup",
        "region",
        "row",
        "rowgroup",
        "rowheader",
        "scrollbar",
        "search",
        "searchbox",
        "separator",
        "slider",
        "spinbutton",
        "status",
        "strong",
        "subscript",
        "superscript",
        "switch",
        "tab",
        "table",
        "tablist",
        "tabpanel",
        "term",
        "textbox",
        "time",
        "timer",
        "toolbar",
        "tooltip",
        "tree",
        "treegrid",
        "treeitem",
    }
)
# Sintaxis de selector que permitiría salir del DOM principal o usar motores internos (M-1):
# `>>` encadena motores (`internal:control=enter-frame`), `internal:` es el motor interno y
# "frame" cubre frame/iframe. Un prefijo `motor=` (xpath=, css=, text=, id=, nth=, _react=,
# data-testid=, ...), un XPath (`//`, `..`) o un texto entrecomillado cambian el motor.
FORBIDDEN_SYNTAX_MESSAGE = "forbidden_selector_syntax"
_FORBIDDEN_SUBSTRINGS = (">>", "internal:", "frame")
_ENGINE_PREFIX = re.compile(r"^\s*[A-Za-z_][\w-]*\s*=")
_SPECIAL_START = re.compile(r"""^\s*(//|\.\.|["'`])""")


def _has_forbidden_syntax(text: str) -> bool:
    folded = "".join(
        ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf"
    ).lower()
    return (
        any(term in folded for term in _FORBIDDEN_SUBSTRINGS)
        or _ENGINE_PREFIX.match(folded) is not None
        or _SPECIAL_START.match(folded) is not None
    )


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
        if any(_has_forbidden_syntax(text) for text in (self.value, self.role, self.name)):
            raise ValueError(FORBIDDEN_SYNTAX_MESSAGE)
        # `PENDIENTE` (plantilla sin validar) lo rechaza después `selectors._has_placeholder`.
        is_placeholder = self.role.strip().upper() == "PENDIENTE"
        if self.strategy == "role" and not is_placeholder and self.role not in ARIA_ROLES:
            raise ValueError("rol ARIA no admitido")
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
