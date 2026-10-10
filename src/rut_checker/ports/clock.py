"""Puerto de reloj (ARQUITECTURA §4): permite probar sin leer la hora del sistema."""

from datetime import date, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Fuente de tiempo inyectable. Ambos valores se expresan en `America/Bogota`.

    La implementación de sistema vive fuera de `ports` (T-35); aquí solo el contrato.
    """

    def now(self) -> datetime:
        """Instante actual, con zona horaria `America/Bogota` (nunca ingenuo)."""
        ...

    def today(self) -> date:
        """Fecha actual en `America/Bogota` (referencia de `evaluate_copy_evidence`)."""
        ...
