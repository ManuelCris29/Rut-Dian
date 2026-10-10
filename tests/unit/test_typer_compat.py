"""Contrato con la API privada de Typer que usa `cli_support` (errores de uso, M-1).

`typer._click` no es API pública: `pyproject.toml` fija `typer>=0.27,<0.28`. Si una
actualización mueve estas clases, esta prueba falla con un mensaje claro antes que la CLI.
"""

import importlib

import pytest

REQUIRED = [
    ("typer._click.core", "Command"),
    ("typer._click.core", "Context"),
    ("typer._click.exceptions", "UsageError"),
    ("typer._click.exceptions", "MissingParameter"),
    ("typer._click.exceptions", "NoArgsIsHelpError"),
    ("typer.core", "TyperCommand"),
    ("typer.core", "TyperGroup"),
]


@pytest.mark.parametrize(("module", "name"), REQUIRED)
def test_private_typer_api_used_by_the_cli_still_exists(module: str, name: str) -> None:
    try:
        loaded = importlib.import_module(module)
    except ImportError:
        pytest.fail(
            f"Typer ya no tiene el módulo {module}: revise cli_support.py y el pin de typer"
        )
    assert hasattr(loaded, name), (
        f"Typer ya no expone {module}.{name}: actualice el import centralizado en "
        "cli_support.py (SafeCommand/SafeGroup) o el pin de typer en pyproject.toml"
    )


def test_usage_error_hierarchy_is_the_expected_one() -> None:
    from typer._click.core import Command
    from typer._click.exceptions import MissingParameter, NoArgsIsHelpError, UsageError

    from rut_checker.cli_support import SafeCommand, SafeGroup

    assert issubclass(MissingParameter, UsageError)
    assert issubclass(NoArgsIsHelpError, UsageError)
    assert issubclass(SafeCommand, Command)
    assert issubclass(SafeGroup, Command)
