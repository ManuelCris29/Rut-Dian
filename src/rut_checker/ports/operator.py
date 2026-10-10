"""Puerto hacia el operador humano para el modo asistido (ADR-0003 §1). Sin lógica."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class OperatorPort(Protocol):
    """Canal de comunicación con la persona que opera la herramienta.

    Los mensajes nunca deben contener la identificación completa (solo enmascarada).
    `runtime_checkable` es una verificación superficial (solo la presencia de los miembros):
    el contrato lo garantiza mypy.
    """

    def notify(self, message: str) -> None:
        """Avisa al operador (p. ej. que debe resolver una verificación de seguridad)."""
        ...

    def confirm_continue(self, message: str) -> bool:
        """Pregunta si se continúa el lote; devuelve `False` si no hay terminal interactiva."""
        ...
