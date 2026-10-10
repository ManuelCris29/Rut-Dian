"""Política de reintentos inyectable (ARQUITECTURA §7).

`RetryPolicy` es el punto de extensión de `BatchQueryService`; `NoRetry` es la política por
defecto y `BackoffRetryPolicy` la real (T-45), construida desde la configuración. Las
salvaguardas del servicio (`bounded_retry_delay`) se aplican siempre, diga lo que diga la política.
"""

import math
from collections.abc import Sequence
from typing import Final, Protocol, Self

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

# Tope fijo de intentos por fila (1 inicial + 2 reintentos); ninguna política lo supera.
MAX_ATTEMPTS: Final = 3
# Estas excepciones nunca se reintentan, diga lo que diga la política (ARQUITECTURA §7).
NEVER_RETRY: Final = (
    HumanInterventionRequired,
    AccessBlocked,
    StructureChanged,
    InvalidIdentification,
    IncompleteResult,
)


class RetryPolicy(Protocol):
    """Decide si una consulta fallida se reintenta y cuánto se espera antes."""

    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        """Segundos a esperar antes de reintentar, o `None` si no se reintenta.

        Args:
            error: Excepción de dominio que acaba de lanzar la fuente.
            attempt: Número (desde 1) del intento que acaba de fallar.
        """
        ...


class NoRetry:
    """Política por defecto: nunca reintenta."""

    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        """Siempre `None`."""
        return None


class RetrySettings(Protocol):
    """Parte de `infra.Settings` que usa la política (`application` no importa `infra`)."""

    @property
    def max_retries(self) -> int:
        """Reintentos de `PortalUnavailable` y `QueryTimeout` (`RUT_MAX_RETRIES`, 0 a 2)."""
        ...

    @property
    def retry_backoff_s(self) -> Sequence[float]:
        """Espera antes de cada reintento (`RUT_RETRY_BACKOFF_S`, p. ej. 30 y 120 s)."""
        ...


class BackoffRetryPolicy:
    """Política real de ARQUITECTURA §7.

    - `PortalUnavailable` y `QueryTimeout`: hasta `max_retries` reintentos; la espera antes del
      reintento *n* es `backoff[n - 1]` (la última si faltan valores).
    - `SessionExpired`: un único reintento (el adaptador abre página nueva), sin espera propia:
      el ritmo mínimo del servicio ya se aplica. Con `max_retries = 0` no se reintenta nada.
    - Cualquier otra excepción (incluida `NEVER_RETRY`): nunca.
    """

    def __init__(self, max_retries: int, backoff_s: Sequence[float]) -> None:
        self._max_retries = max_retries
        self._backoff_s = tuple(backoff_s)

    @classmethod
    def from_settings(cls, settings: RetrySettings) -> Self:
        """Construye la política desde `RUT_MAX_RETRIES` y `RUT_RETRY_BACKOFF_S`."""
        return cls(settings.max_retries, settings.retry_backoff_s)

    def delay_before_retry(self, error: RutCheckerError, attempt: int) -> float | None:
        """Segundos a esperar antes de reintentar, o `None` si no se reintenta."""
        if isinstance(error, NEVER_RETRY):
            return None
        if isinstance(error, SessionExpired):
            return 0.0 if attempt <= min(1, self._max_retries) else None
        if isinstance(error, PortalUnavailable | QueryTimeout):
            if attempt > self._max_retries or not self._backoff_s:
                return None
            return float(self._backoff_s[min(attempt, len(self._backoff_s)) - 1])
        return None


def bounded_retry_delay(policy: RetryPolicy, error: RutCheckerError, attempt: int) -> float | None:
    """Espera para reintentar tras aplicar las salvaguardas del servicio, o `None`.

    No se reintenta si el error es de `NEVER_RETRY`, si se alcanzó `MAX_ATTEMPTS` o si la
    política devuelve un retraso no finito o negativo.
    """
    if isinstance(error, NEVER_RETRY) or attempt >= MAX_ATTEMPTS:
        return None
    delay = policy.delay_before_retry(error, attempt)
    if delay is None or not math.isfinite(delay) or delay < 0:
        return None
    return delay
