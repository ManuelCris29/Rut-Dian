"""Configuración de la aplicación (ARQUITECTURA §9, ADR-0002 §3).

Los valores por defecto son seguros: fuente `contingency`, portal deshabilitado, `fake` no
permitido, snapshot de diagnóstico apagado y navegador visible. La verificación de la triple
llave del portal (habilitación + referencia de aprobación) y de `selectors.yaml` ocurre en
`build_service` (T-37/T-40); aquí solo se validan los valores y su coherencia.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SourceName = Literal["contingency", "dian_portal", "fake"]

_APPROVAL_REF_PATTERN = re.compile(r"^APR-\d{8}-\d{1,3}$")
_DIAN_HOST_PATTERN = re.compile(r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+dian\.gov\.co")
_DEFAULT_PORTAL_URL = "https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces"
MIN_DELAY_S = 3.0


def is_valid_approval_ref(value: str) -> bool:
    """Indica si `value` tiene el formato `APR-AAAAMMDD-n` (1 a 3 dígitos finales)."""
    if _APPROVAL_REF_PATTERN.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value[4:12], "%Y%m%d")  # solo se valida la fecha
    except ValueError:
        return False
    return True


def is_valid_portal_url(value: str) -> bool:
    """Indica si `value` es una URL https hacia un host `*.dian.gov.co` (puerto 443, sin userinfo).

    Rechaza de entrada la barra invertida, espacios y caracteres de control: los navegadores
    (WHATWG) tratan la barra invertida como `/`, así que `https://evil.com` seguido de una barra
    invertida y `.dian.gov.co` navegaría a `evil.com`.
    """
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char == "\\" for char in value):
        return False
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and "@" not in parts.netloc
        and port in (None, 443)
        and _DIAN_HOST_PATTERN.fullmatch(host) is not None
    )


class Settings(BaseSettings):
    """Configuración inmutable, leída de variables `RUT_*` (y de `.env` si existe)."""

    model_config = SettingsConfigDict(
        env_prefix="RUT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Fuente y triple llave del portal
    source: SourceName = "contingency"
    allow_fake: bool = False
    portal_enabled: bool = False
    portal_approval_ref: str = ""
    portal_url: str = _DEFAULT_PORTAL_URL
    selectors_path: Path = Path("config/selectors.yaml")

    # Navegador y modo asistido
    headless: bool = False
    navigation_timeout_s: int = Field(default=30, gt=0, le=300)
    human_challenge_timeout_s: int = Field(default=120, ge=30, le=900)

    # Ritmo responsable y reintentos
    min_delay_between_queries_s: float = Field(
        default=5.0, ge=MIN_DELAY_S, le=600, allow_inf_nan=False
    )
    max_retries: int = Field(default=2, ge=0, le=2)
    retry_backoff_s: Annotated[tuple[int, ...], NoDecode] = (30, 120)

    # Lote y retención
    max_batch_size: int = Field(default=200, ge=1, le=200)
    retention_days: int = Field(default=365, ge=1, le=365)

    # Diagnóstico (D-5): apagado por defecto
    diagnostic_snapshot: bool = False

    # Carpetas locales
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")

    @field_validator("retry_backoff_s", mode="before")
    @classmethod
    def _parse_backoff(cls, value: object) -> object:
        """Acepta `"30,120"` (formato `.env`) además de secuencias ya parseadas."""
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("retry_backoff_s")
    @classmethod
    def _backoff_positive(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(seconds <= 0 for seconds in value):
            raise ValueError("RUT_RETRY_BACKOFF_S debe contener segundos positivos")
        return value

    @field_validator("portal_approval_ref")
    @classmethod
    def _approval_ref_format(cls, value: str) -> str:
        if value and not is_valid_approval_ref(value):
            raise ValueError(
                "RUT_PORTAL_APPROVAL_REF debe ser vacío o tener formato APR-AAAAMMDD-n"
            )
        return value

    @field_validator("portal_url")
    @classmethod
    def _portal_url_is_dian_https(cls, value: str) -> str:
        if not is_valid_portal_url(value):
            raise ValueError("RUT_PORTAL_URL debe ser https con host *.dian.gov.co (puerto 443)")
        return value

    @model_validator(mode="after")
    def _check_coherence(self) -> Self:
        if len(self.retry_backoff_s) < self.max_retries:
            raise ValueError("RUT_RETRY_BACKOFF_S debe tener al menos RUT_MAX_RETRIES valores")
        if any(seconds < MIN_DELAY_S for seconds in self.retry_backoff_s):
            raise ValueError("RUT_RETRY_BACKOFF_S: cada espera debe ser de al menos 3 s")
        if self.source == "dian_portal" and self.headless:
            raise ValueError("RUT_SOURCE=dian_portal exige RUT_HEADLESS=false (headless prohibido)")
        if self.diagnostic_snapshot and not is_valid_approval_ref(self.portal_approval_ref):
            raise ValueError(
                "RUT_DIAGNOSTIC_SNAPSHOT=true exige RUT_PORTAL_APPROVAL_REF con formato válido"
            )
        return self
