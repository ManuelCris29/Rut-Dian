"""Reloj de sistema y `Sleeper` inyectable (ARQUITECTURA §3 y §4).

`Clock` es un puerto (`ports/clock.py`); aquí solo vive su implementación de sistema y el
`Sleeper`, que permite probar esperas sin dormir de verdad.
"""

import time
from datetime import date, datetime
from typing import Final, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

_BOGOTA: Final = ZoneInfo("America/Bogota")


@runtime_checkable
class Sleeper(Protocol):
    """Espera inyectable (ritmo entre consultas y backoff)."""

    def sleep(self, seconds: float) -> None:
        """Detiene la ejecución `seconds` segundos."""
        ...


class SystemSleeper:
    """`Sleeper` real: bloquea el hilo con `time.sleep`."""

    def sleep(self, seconds: float) -> None:
        """Detiene la ejecución `seconds` segundos."""
        time.sleep(seconds)


class SystemClock:
    """`Clock` real, siempre en `America/Bogota`."""

    def now(self) -> datetime:
        """Instante actual con zona horaria `America/Bogota`."""
        return datetime.now(_BOGOTA)

    def today(self) -> date:
        """Fecha actual en `America/Bogota` (derivada de `now()`)."""
        return self.now().date()
