"""Pruebas de `ConsoleOperator` (ADR-0003 §1): avisos por stderr y confirmación segura."""

import pytest
import typer
from typer.testing import CliRunner

from rut_checker.adapters.console_operator import ConsoleOperator
from rut_checker.ports.operator import OperatorPort

runner = CliRunner()


def _app(operator: ConsoleOperator, action: str, message: str) -> typer.Typer:
    app = typer.Typer()

    @app.command()
    def run() -> None:
        if action == "notify":
            operator.notify(message)
        else:
            typer.echo("yes" if operator.confirm_continue(message) else "no")

    @app.command()
    def other() -> None:  # segundo comando: evita que Typer colapse a comando único
        pass

    return app


def test_is_an_operator_port() -> None:
    assert isinstance(ConsoleOperator(), OperatorPort)


def test_notify_goes_to_stderr_and_masks_digit_runs() -> None:
    result = runner.invoke(_app(ConsoleOperator(), "notify", "fila 1000000001 pendiente"), ["run"])
    assert "1000000001" not in result.stdout
    assert "1000000001" not in result.stderr
    assert "fila" in result.stderr
    assert result.stdout == ""


def test_confirm_without_terminal_is_false_and_does_not_prompt() -> None:
    operator = ConsoleOperator(is_interactive=lambda: False)
    result = runner.invoke(_app(operator, "confirm", "¿Continuar?"), ["run"], input="y\n")
    assert result.stdout.strip() == "no"


@pytest.mark.parametrize(("typed", "expected"), [("y\n", "yes"), ("n\n", "no"), ("", "no")])
def test_confirm_with_terminal_follows_answer_and_eof_is_false(typed: str, expected: str) -> None:
    operator = ConsoleOperator(is_interactive=lambda: True)
    result = runner.invoke(_app(operator, "confirm", "¿Continuar?"), ["run"], input=typed)
    assert result.stdout.strip().endswith(expected)
