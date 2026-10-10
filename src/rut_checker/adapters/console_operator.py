"""`ConsoleOperator`: canal con el operador por consola (ADR-0003 §1, modo asistido).

Los avisos van a stderr; la confirmación solo se pregunta si hay terminal interactiva. Sin
terminal (stdin no es tty), ante EOF o ante Ctrl+C en la pregunta, la respuesta es `False`:
sin respuesta humana el lote se detiene (ADR-0003 §4). Los mensajes pasan por `mask_digit_runs`
como defensa extra: nunca deben contener una identificación completa.
"""

import sys
from collections.abc import Callable

import typer

from rut_checker.domain.masking import mask_digit_runs


def stdin_is_tty() -> bool:
    """Indica si stdin es una terminal interactiva (`False` si está cerrado o reemplazado)."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):  # stdin cerrado o reemplazado
        return False


class ConsoleOperator:
    """Implementación de `OperatorPort` sobre Typer."""

    def __init__(self, is_interactive: Callable[[], bool] = stdin_is_tty) -> None:
        """Crea el operador.

        Args:
            is_interactive: Indica si hay una persona frente a la terminal (inyectable).
        """
        self._is_interactive = is_interactive

    def notify(self, message: str) -> None:
        """Muestra un aviso por stderr."""
        typer.echo(mask_digit_runs(message), err=True)

    def confirm_continue(self, message: str) -> bool:
        """Pregunta si se continúa; `False` sin terminal interactiva o sin respuesta."""
        if not self._is_interactive():
            return False
        try:
            return typer.confirm(mask_digit_runs(message), default=False, err=True)
        except (typer.Abort, EOFError):
            return False
