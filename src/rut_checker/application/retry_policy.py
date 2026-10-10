"""Política de reintentos inyectable (ARQUITECTURA §7).

T-35 solo define el punto de extensión y la política por defecto (sin reintentos). La política
real (qué excepciones, cuántos intentos, backoff `RUT_RETRY_BACKOFF_S`, circuito) es de T-45 y
se inyecta en `BatchQueryService` sin modificarlo.
"""

import math
from typing import Final, Protocol

from rut_checker.domain.errors import (
    AccessBlocked,
    HumanInterventionRequired,
    IncompleteResult,
    InvalidIdentification,
    RutCheckerError,
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
