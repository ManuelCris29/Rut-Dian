"""Dobles de prueba compartidos (no forman parte del paquete de producción)."""

from collections.abc import Iterable
from typing import Literal

type EventKind = Literal["notify", "confirm"]


class OperatorDouble:
    """Doble de `OperatorPort`: registra eventos y responde confirmaciones programadas.

    `events` es la única fuente de verdad (tipo, mensaje) en orden cronológico.
    Cuando se agotan las confirmaciones programadas responde `default_confirm`
    (`False`, igual que `ConsoleOperator` sin terminal interactiva).
    """

    def __init__(
        self, confirmations: Iterable[bool] = (), *, default_confirm: bool = False
    ) -> None:
        self._pending = list(confirmations)
        self._default_confirm = default_confirm
        self.events: list[tuple[EventKind, str]] = []

    def notify(self, message: str) -> None:
        self.events.append(("notify", message))

    def confirm_continue(self, message: str) -> bool:
        self.events.append(("confirm", message))
        return self._pending.pop(0) if self._pending else self._default_confirm

    @property
    def notifications(self) -> list[str]:
        return [m for kind, m in self.events if kind == "notify"]

    @property
    def confirm_prompts(self) -> list[str]:
        return [m for kind, m in self.events if kind == "confirm"]

    @property
    def all_messages(self) -> list[str]:
        """Todos los mensajes (avisos y preguntas) en orden cronológico."""
        return [m for _, m in self.events]

    def messages_containing(self, text: str) -> list[str]:
        """Mensajes que contienen `text` (p. ej. una identificación completa)."""
        return [m for m in self.all_messages if text in m]

    def assert_no_full_identification(self, *identifications: str) -> None:
        """Falla si algún mensaje contiene alguna de las identificaciones completas."""
        leaked = {i: self.messages_containing(i) for i in identifications}
        assert not any(leaked.values()), "mensaje al operador con identificación completa"
