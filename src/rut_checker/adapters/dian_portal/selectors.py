"""Validación de `config/selectors.yaml` y puerta única del portal (llave 3, ADR-0002 §3).

Solo implementa el mecanismo: ningún valor real de selector. Mientras el archivo del repositorio
tenga `PENDIENTE` y `validated: false` (T-14 bloqueada), `ensure_portal_enabled` falla siempre.

- `location.py`: raíz anclada al paquete y ubicación segura (B-1); `yaml_loader.py`: lectura
  acotada y estricta (pyyaml perezoso, extra `portal`); `models.py`: modelos Pydantic.
- Puerta única: `ensure_portal_enabled` devuelve `EnabledPortal`, el único tipo que acepta
  `DianPortalSource` (T-49). Para pruebas existe una vía explícita
  (`enabled_portal_from_synthetic_fixture`, limitada a `tests/fixtures/`) y funciones privadas con
  la raíz inyectada; `build_service` solo debe llamar a `ensure_portal_enabled`.
- Los errores llevan un motivo cerrado: nunca rutas ni valores del YAML.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from rut_checker.adapters.dian_portal.location import (
    _check_location,
    _is_link,
    _project_root,
    _snapshot_exists,
)
from rut_checker.adapters.dian_portal.models import (
    DetectionSelectors,
    PortalSelectors,
    SelectorSpec,
)
from rut_checker.adapters.dian_portal.yaml_loader import MAX_SELECTORS_FILE_BYTES, read_yaml
from rut_checker.domain.errors import (
    SelectorsNotValidatedError,
    SelectorsReason,
    SourceNotEnabledError,
    SourceNotEnabledReason,
)
from rut_checker.infra.settings import Settings, is_valid_approval_ref, is_valid_portal_url

__all__ = [
    "MAX_SELECTORS_FILE_BYTES",
    "RESERVED_SYNTHETIC_APPROVAL_REF",
    "EnabledPortal",
    "PortalSelectors",
    "enabled_portal_from_synthetic_fixture",
    "ensure_portal_enabled",
    "load_selectors",
]

RESERVED_SYNTHETIC_APPROVAL_REF = "APR-19700101-0"  # reservada a fixtures; producción la rechaza
# `PENDIENTE` como palabra completa (sin falsos positivos en "independiente").
_PLACEHOLDER = re.compile(r"(?<![^\W_])PENDIENTE(?![^\W_])")
# Términos del desafío que ni el formulario ni el resultado pueden usar como objetivo (M-2).
# Se comparan también con "_" reemplazado por "-" (p. ej. `__cf_chl_tk`).
_FORBIDDEN_TARGET_TERMS = (
    "turnstile",
    "challenges.cloudflare",
    "challenge-platform",
    "cf-chl",
    "cf_chl",
    "cdn-cgi",
    "cloudflare",
    "challenge",
    "captcha",
    "recaptcha",
    "hcaptcha",
    "geetest",
    "arkose",
)

_TOKEN = object()


class EnabledPortal:
    """Portal habilitado: envuelve selectores ya verificados por la triple llave.

    Solo este módulo lo construye (token privado): `DianPortalSource` acepta únicamente este
    tipo, de modo que no puede recibir selectores sin pasar por `ensure_portal_enabled`. Es una
    barrera contra errores de cableado, no contra código malicioso en el mismo proceso.
    """

    __slots__ = ("_selectors", "_synthetic")
    _selectors: PortalSelectors
    _synthetic: bool

    def __init__(self, selectors: PortalSelectors, *, synthetic: bool, _token: object) -> None:
        if _token is not _TOKEN:
            raise TypeError("EnabledPortal solo se crea con ensure_portal_enabled")
        object.__setattr__(self, "_selectors", selectors)
        object.__setattr__(self, "_synthetic", synthetic)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("EnabledPortal es inmutable")

    @property
    def selectors(self) -> PortalSelectors:
        """Selectores verificados."""
        return self._selectors

    @property
    def synthetic(self) -> bool:
        """`True` solo en la vía de pruebas con selectores sintéticos."""
        return self._synthetic


def _parse_file(path: Path) -> PortalSelectors:
    """Lee y valida la estructura (sin comprobar la ubicación ni la triple llave)."""
    try:
        return PortalSelectors.model_validate(read_yaml(path))
    except ValidationError:
        raise SelectorsNotValidatedError(SelectorsReason.INVALID_STRUCTURE) from None


def _normalize(text: str) -> str:
    """NFKC sin caracteres de formato (Cf, p. ej. ancho cero), para comparar sin evasiones."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def _strings(value: object) -> list[str]:
    """Todas las cadenas contenidas en una estructura de dicts/listas."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _has_placeholder(selectors: PortalSelectors) -> bool:
    return any(
        _PLACEHOLDER.search(_normalize(text).upper()) is not None
        for text in _strings(selectors.model_dump())
    )


def _targets_challenge(selectors: PortalSelectors) -> bool:
    """`form.*` o `result.*` que apuntan al desafío (los `challenge_markers` sí pueden)."""
    specs: list[SelectorSpec | None] = [
        selectors.form.id_input,
        selectors.form.submit_button,
        selectors.result.status,
        selectors.result.name,
        selectors.result.no_result_msg,
    ]
    texts = (
        _normalize(text).lower()
        for spec in specs
        if spec is not None
        for text in (spec.value, spec.role, spec.name)
    )
    return any(
        term in variant
        for text in texts
        for variant in (text, text.replace("_", "-"))
        for term in _FORBIDDEN_TARGET_TERMS
    )


def _observed_none(detection: DetectionSelectors, kind: Literal["challenge", "block"]) -> bool:
    """`*_observed: none` con evidencia (referencia al snapshot) no vacía."""
    if kind == "challenge":
        return detection.challenge_observed == "none" and bool(detection.challenge_evidence.strip())
    return detection.block_observed == "none" and bool(detection.block_evidence.strip())


def _check_ready(selectors: PortalSelectors, approval_ref: str, root: Path) -> None:
    """Aplica las condiciones de la llave 3 en orden fijo; cada fallo tiene su motivo."""
    if selectors.synthetic or RESERVED_SYNTHETIC_APPROVAL_REF in (
        selectors.approval_ref,
        approval_ref,
    ):
        raise SelectorsNotValidatedError(SelectorsReason.SYNTHETIC)
    if not selectors.validated:
        raise SelectorsNotValidatedError(SelectorsReason.NOT_VALIDATED)
    if not is_valid_approval_ref(approval_ref):
        raise SelectorsNotValidatedError(SelectorsReason.INVALID_APPROVAL_REF)
    if selectors.approval_ref != approval_ref:
        raise SelectorsNotValidatedError(SelectorsReason.APPROVAL_MISMATCH)
    if not _snapshot_exists(selectors.source_snapshot, root):
        raise SelectorsNotValidatedError(SelectorsReason.SNAPSHOT_MISSING)
    if _has_placeholder(selectors):
        raise SelectorsNotValidatedError(SelectorsReason.PLACEHOLDER)
    if _targets_challenge(selectors):
        raise SelectorsNotValidatedError(SelectorsReason.FORBIDDEN_TARGET)
    detection = selectors.detection
    if not any(marker.strip() for marker in detection.maintenance_url_markers):
        raise SelectorsNotValidatedError(SelectorsReason.MAINTENANCE_MARKERS_EMPTY)
    if not (detection.challenge_markers or _observed_none(detection, "challenge")):
        raise SelectorsNotValidatedError(SelectorsReason.CHALLENGE_MARKERS_MISSING)
    if not (detection.block_markers or _observed_none(detection, "block")):
        raise SelectorsNotValidatedError(SelectorsReason.BLOCK_MARKERS_MISSING)


def _load_validated(path: Path, approval_ref: str, root: Path) -> PortalSelectors:
    """Carga con la raíz inyectada. SOLO PARA PRUEBAS: `build_service` no debe usarla."""
    root = root.resolve()
    _check_location(path, root)
    selectors = _parse_file(path)
    _check_ready(selectors, approval_ref, root)
    return selectors


def load_selectors(path: Path, approval_ref: str) -> PortalSelectors:
    """Carga y valida `selectors.yaml`; falla si no cumple la llave 3.

    No habilita el portal: el adaptador solo acepta el `EnabledPortal` de `ensure_portal_enabled`.

    Args:
        path: debe resolver exactamente a `<raíz del proyecto>/config/selectors.yaml`; la raíz
            se deduce del paquete, no de `path`. Una ruta relativa se interpreta desde el cwd.
        approval_ref: valor de `RUT_PORTAL_APPROVAL_REF`; debe ser igual al del archivo.

    Raises:
        SelectorsNotValidatedError: con un motivo cerrado, sin rutas ni valores del YAML.
    """
    return _load_validated(path, approval_ref, _project_root())


def _ensure_enabled(settings: Settings, root: Path) -> EnabledPortal:
    """Triple llave con la raíz inyectada. SOLO PARA PRUEBAS: `build_service` no debe usarla."""
    if not settings.portal_enabled:
        raise SourceNotEnabledError(SourceNotEnabledReason.FLAG_DISABLED)
    if not is_valid_approval_ref(settings.portal_approval_ref):
        raise SourceNotEnabledError(SourceNotEnabledReason.MISSING_APPROVAL_REF)
    if not is_valid_portal_url(settings.portal_url):
        raise SourceNotEnabledError(SourceNotEnabledReason.INVALID_URL)
    if settings.headless:
        raise SourceNotEnabledError(SourceNotEnabledReason.HEADLESS_NOT_ALLOWED)
    selectors = _load_validated(settings.selectors_path, settings.portal_approval_ref, root)
    return EnabledPortal(selectors, synthetic=False, _token=_TOKEN)


def ensure_portal_enabled(settings: Settings) -> EnabledPortal:
    """Verifica la triple llave completa antes de abrir el navegador (sin red).

    Llave 1: `portal_enabled` y `portal_approval_ref` válida. Llave 2: URL del portal válida y
    navegador visible. Llave 3: `selectors.yaml` validado con la misma referencia de aprobación.

    Returns:
        `EnabledPortal` con los selectores verificados: la única entrada que acepta
        `DianPortalSource`.

    Raises:
        SourceNotEnabledError: falla de las llaves 1 o 2.
        SelectorsNotValidatedError: falla de la llave 3.
    """
    return _ensure_enabled(settings, _project_root())


def enabled_portal_from_synthetic_fixture(path: Path) -> EnabledPortal:
    """Vía EXPLÍCITA de pruebas (T-38/T-49): selectores sintéticos de `tests/fixtures/`.

    Solo acepta archivos con `synthetic: true` bajo `<raíz>/tests/fixtures/` (sin enlaces). El
    resultado queda marcado `synthetic=True`. `build_service` no debe importar esta función
    (una prueba de arquitectura lo verifica).
    """
    fixtures = (_project_root() / "tests" / "fixtures").resolve()
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        raise SelectorsNotValidatedError(SelectorsReason.OUTSIDE_PROJECT) from None
    if not resolved.is_relative_to(fixtures) or _is_link(Path(os.path.abspath(path))):
        raise SelectorsNotValidatedError(SelectorsReason.OUTSIDE_PROJECT)
    selectors = _parse_file(resolved)
    if not selectors.synthetic:
        raise SelectorsNotValidatedError(SelectorsReason.NOT_SYNTHETIC)
    return EnabledPortal(selectors, synthetic=True, _token=_TOKEN)
