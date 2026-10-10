"""Dobles de prueba compartidos (no forman parte del paquete de producción)."""

from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from rut_checker.ports.clock import Clock

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


BOGOTA = ZoneInfo("America/Bogota")


class FixedClock:
    """Doble de `Clock`: instante fijo, sin leer el reloj del sistema."""

    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("el reloj fijo exige un instante con zona horaria")
        self._moment = moment

    @classmethod
    def on(cls, day: date) -> "FixedClock":
        """Reloj fijo a mediodía (hora de Bogotá) del día indicado."""
        return cls(datetime(day.year, day.month, day.day, 12, 0, tzinfo=BOGOTA))

    def now(self) -> datetime:
        """Instante fijo (con zona horaria)."""
        return self._moment

    def today(self) -> date:
        """Fecha de `now()` en America/Bogota (derivada, nunca independiente)."""
        return self._moment.astimezone(BOGOTA).date()


class FakeSleeper:
    """Doble de `Sleeper`: registra las esperas pedidas sin dormir de verdad."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def assert_clock_contract(clock: "Clock") -> None:
    """Contrato de todo `Clock` (reutilizable para `SystemClock` en T-35)."""
    now = clock.now()
    assert now.tzinfo is not None, "now() debe tener zona horaria"
    assert clock.today() == now.astimezone(BOGOTA).date()
