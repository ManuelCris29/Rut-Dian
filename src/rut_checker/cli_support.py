"""Apoyo de la CLI (T-40): configuración, avisos, resumen y traducción de errores a códigos.

Toda salida a consola pasa por aquí o por `cli.py` y nunca incluye una identificación completa,
un valor de configuración ni el texto de una excepción: solo mensajes propios, motivos cerrados
y clases de excepción (Obs-3). Los códigos de salida son los de ARQUITECTURA §6.
"""

import io
import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final, NoReturn

import typer
from pydantic import ValidationError
from pydantic_settings import SettingsError

# ÚNICO acceso a la API privada de Typer (UsageError/Command/Context no son públicos; el click
# vendido vive en `typer._click`): pin `typer>=0.27,<0.28` y tests/unit/test_typer_compat.py.
from typer._click.core import Command, Context
from typer._click.exceptions import MissingParameter, NoArgsIsHelpError, UsageError
from typer.core import TyperCommand, TyperGroup

from rut_checker.application.report import BatchReport
from rut_checker.application.row_results import masked_id
from rut_checker.domain.errors import (
    ExportError,
    FakeNotAllowedError,
    InvalidInputFile,
    SelectorsNotValidatedError,
    SourceNotEnabledError,
    UnsafePathError,
)
from rut_checker.domain.status import QueryStatus
from rut_checker.infra.paths import assert_safe_dir, ensure_private_dir, is_synced_folder
from rut_checker.infra.retention import find_expired
from rut_checker.infra.settings import Settings
from rut_checker.io.exporters import ExportKind, ExportReport
from rut_checker.ports.clock import Clock

EXIT_OK: Final = 0
EXIT_STOPPED: Final = 1
EXIT_INPUT: Final = 2
EXIT_EXPORT: Final = 3

_PORTAL_HINT: Final = (
    "Para usar el portal deben estar registradas las condiciones (a) a (d) de "
    "INFORME-VIABILIDAD §8 en docs/ESTADO.md (referencia APR-AAAAMMDD-n) y los "
    "selectores validados. Use RUT_SOURCE=contingency mientras tanto."
)


def echo_err(message: str) -> None:
    """Escribe un mensaje propio (sin datos personales) por stderr."""
    typer.echo(message, err=True)


def fail(message: str, code: int) -> NoReturn:
    """Muestra `message` por stderr y termina con `code`."""
    echo_err(message)
    raise typer.Exit(code)


def new_run_id(clock: Clock) -> str:
    """Identificador de ejecución `AAAAMMDD-HHMMSS-<4 hex>` (hora de Bogotá)."""
    return f"{clock.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


# --- configuración -------------------------------------------------------------------------


def load_settings() -> Settings:
    """Lee `Settings`; ante valores inválidos termina con código 2 citando solo los nombres."""
    try:
        return Settings()
    except ValidationError as error:
        names = sorted({_variable_name(item["loc"]) for item in _field_errors(error)})
        named = [name for name in names if name]
        detail = f"Revise: {', '.join(named)}." if named else "Revise la coherencia entre ellas."
        message = f"Configuración inválida. {detail}"
    except SettingsError:
        message = "Configuración inválida: no se pudieron leer las variables RUT_*."
    fail(message, EXIT_INPUT)


def _field_errors(error: ValidationError) -> list[dict[str, tuple[int | str, ...]]]:
    # Solo `loc`: el valor de entrada (`input`) puede traer datos y no se lee nunca.
    return [
        {"loc": item["loc"]}
        for item in error.errors(include_input=False, include_url=False, include_context=False)
    ]


def _variable_name(loc: tuple[int | str, ...]) -> str:
    return f"RUT_{loc[0]}".upper() if loc and isinstance(loc[0], str) else ""


def env_file_notice() -> str | None:
    """Aviso de qué `.env` se cargó (solo la ruta, nunca su contenido)."""
    configured = Settings.model_config.get("env_file")
    if not isinstance(configured, str | Path):
        return None
    path = Path(configured)
    return f"Configuración cargada desde {path.resolve()}" if path.is_file() else None


def prepare_run_dirs(settings: Settings, output_dir: Path | None = None) -> None:
    """Valida `data/` y `logs/` y crea de forma privada `output/` y `logs/` (Obs-4).

    `logs/` se crea al final: si algo falla antes no queda ninguna carpeta de logs.

    Args:
        settings: Configuración con las carpetas.
        output_dir: Carpeta de salida efectiva (`--salida`); por defecto `RUT_OUTPUT_DIR`.

    Raises:
        UnsafePathError: alguna carpeta está en un árbol git no permitido o es inválida.
    """
    assert_safe_dir(settings.data_dir)
    assert_safe_dir(settings.log_dir)
    ensure_private_dir(settings.output_dir)
    if output_dir is not None and output_dir != settings.output_dir:
        ensure_private_dir(output_dir)
    ensure_private_dir(settings.log_dir)


def force_utf8_output() -> None:
    """Con salida redirigida (no terminal) fuerza UTF-8 en stdout/stderr (RNF-06).

    En Windows una tubería usa cp1252 y las tildes saldrían corruptas. En terminal no se toca.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and not stream.closed and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")


# --- avisos --------------------------------------------------------------------------------


def announce_environment(settings: Settings, clock: Clock) -> None:
    """Avisos previos a la ejecución: `.env`, datos de prueba, nube y archivos vencidos."""
    notice = env_file_notice()
    if notice is not None:
        echo_err(notice)
    if settings.source == "fake":
        echo_err("AVISO: DATOS DE PRUEBA (fuente fake). Los resultados no son válidos.")
    folders = {
        "RUT_DATA_DIR": settings.data_dir,
        "RUT_OUTPUT_DIR": settings.output_dir,
        "RUT_LOG_DIR": settings.log_dir,
    }
    for name, folder in folders.items():
        if is_synced_folder(folder):
            echo_err(
                f"AVISO: {name} parece estar en una carpeta que se sincroniza con la nube; "
                "use una carpeta local no sincronizada."
            )
    expired = find_expired(
        list(folders.values()), clock.now(), max_age_days=settings.retention_days
    )
    if expired:
        echo_err(
            f"Hay {len(expired)} archivos con más de {settings.retention_days} días: "
            "ejecute `rut-checker purgar`"
        )


# --- resumen y código de salida ------------------------------------------------------------


def _count_lines(report: BatchReport) -> list[str]:
    counts = report.counts
    return [f"  {status.value}: {counts[status]}" for status in QueryStatus if status in counts]


def render_summary(report: BatchReport, export: ExportReport | None, run_id: str) -> None:
    """Resumen en consola: conteos por estado, parada y ruta del archivo (sin ids)."""
    typer.echo(f"Ejecución {run_id}: {len(report.outcomes)} filas")
    for line in _count_lines(report):
        typer.echo(line)
    if report.stop_reason is not None:
        typer.echo(
            f"Lote detenido ({report.stop_reason.value}): las filas restantes quedaron "
            "pendientes de validación manual."
        )
    if export is None:
        return
    if export.kind is ExportKind.JSON_BACKUP:
        echo_err(
            f"No se pudo escribir el Excel: se guardó un respaldo JSON en {export.path}. "
            "Revise que el archivo no esté abierto."
        )
    elif export.kind is ExportKind.XLSX_ALTERNATIVE:
        typer.echo(f"El archivo previsto estaba en uso; Excel escrito en {export.path}")
    else:
        typer.echo(f"Excel: {export.path}")


def render_single_row(report: BatchReport) -> None:
    """Línea por fila (solo para `consultar`): id enmascarado, estado y fuente."""
    for outcome in report.outcomes:
        shown = masked_id(outcome.row, outcome.identification) or "(sin número)"
        result = outcome.result
        typer.echo(
            f"Fila {outcome.row.row_index + 1}: {shown} -> {result.status.value} "
            f"[{result.source.value}]"
        )


def exit_code(report: BatchReport, export: ExportReport, *, single: bool = False) -> int:
    """3 sin Excel (respaldo JSON); 2 si `consultar` recibió un número inválido; 1 si se detuvo."""
    if export.kind is ExportKind.JSON_BACKUP:
        return EXIT_EXPORT
    if single and report.counts.get(QueryStatus.ENTRADA_INVALIDA):
        return EXIT_INPUT
    return EXIT_STOPPED if report.stopped else EXIT_OK


# --- errores -------------------------------------------------------------------------------


KNOWN_ERRORS: Final = (
    SourceNotEnabledError,
    SelectorsNotValidatedError,
    FakeNotAllowedError,
    UnsafePathError,
    InvalidInputFile,
    ExportError,
)


def unexpected_message(error: Exception, *, logged: bool) -> str:
    """Mensaje de un fallo inesperado: solo la clase; remite al log solo si existe."""
    base = (
        f"Error inesperado ({type(error).__name__}). "
        "No se muestran detalles por protección de datos"
    )
    return f"{base}; revise el log de la ejecución." if logged else f"{base}."


def _classify(error: Exception) -> tuple[str, int]:
    """Mensaje seguro y código para una excepción (solo textos propios o motivos cerrados)."""
    if isinstance(error, SourceNotEnabledError | SelectorsNotValidatedError):
        return f"{error}" + chr(10) + _PORTAL_HINT, EXIT_INPUT
    if isinstance(error, FakeNotAllowedError | UnsafePathError | InvalidInputFile):
        return str(error), EXIT_INPUT
    if isinstance(error, ExportError):
        return str(error), EXIT_EXPORT
    return unexpected_message(error, logged=False), EXIT_STOPPED


@contextmanager
def handled_errors() -> Iterator[None]:
    """Traduce las excepciones a mensaje y código de salida, sin traceback ni locales."""
    try:
        yield
        return
    except (typer.Exit, typer.Abort):
        raise
    except Exception as error:  # última línea de defensa: nada de traceback con datos
        outcome = _classify(error)
    fail(*outcome)


# --- errores de uso de Click ---------------------------------------------------------------

_USAGE_MESSAGE: Final = "Uso incorrecto; revise --help. No se repiten los valores escritos."


def _generic_usage(ctx: Context) -> UsageError:
    return UsageError(_USAGE_MESSAGE, ctx)


class SafeCommand(TyperCommand):
    """Comando cuyos errores de uso no repiten lo escrito (p. ej. un número de más)."""

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        """Como el original, pero un `UsageError` se reemplaza por un mensaje genérico."""
        try:
            return super().parse_args(ctx, args)
        except (MissingParameter, NoArgsIsHelpError):
            raise  # solo nombran el parámetro; la ayuda sin argumentos es legítima
        except UsageError:
            raise _generic_usage(ctx) from None


class SafeGroup(TyperGroup):
    """Grupo cuyo error de subcomando desconocido no repite el texto escrito."""

    def resolve_command(
        self, ctx: Context, args: list[str]
    ) -> tuple[str | None, Command | None, list[str]]:
        """Como el original, pero un subcomando desconocido da un mensaje genérico."""
        try:
            return super().resolve_command(ctx, args)
        except UsageError:
            raise _generic_usage(ctx) from None
