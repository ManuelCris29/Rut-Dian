"""CLI de `rut-checker` (ARQUITECTURA §6).

Comandos: `lote <archivo> [--salida DIR] [--formato ...]`, `consultar [NUMERO] [--dv ...]`
y `purgar`
(lógica en `cli_purge.py`). Códigos de salida:
0 completo, 1 lote detenido (o fallo inesperado), 2 entrada/configuración/ruta, 3 exportación.

Decisiones:
- El cableado (`build_service`) vive en `wiring.py`; aquí solo se usa.
- El número del comando `consultar` se pide por prompt sin eco (Obs-11, evita el historial).
"""

import logging
from pathlib import Path
from typing import Annotated, Final

import typer

from rut_checker.adapters.console_operator import stdin_is_tty
from rut_checker.application.clock import SystemClock
from rut_checker.application.report import BatchReport
from rut_checker.cli_purge import run_purge
from rut_checker.cli_render import (
    check_output_extension,
    exit_code,
    render_single_row,
    render_summary,
)
from rut_checker.cli_support import (
    EXIT_INPUT,
    EXIT_STOPPED,
    KNOWN_ERRORS,
    SafeCommand,
    SafeGroup,
    announce_environment,
    echo_err,
    fail,
    force_utf8_output,
    handled_errors,
    load_settings,
    new_run_id,
    unexpected_message,
)
from rut_checker.domain.errors import ExportError
from rut_checker.domain.models import InputRow
from rut_checker.domain.status import SourceKind
from rut_checker.infra.logging import (
    close_run_logging,
    configure_logging,
    log_exception,
    log_export_failed,
    silence_unconfigured_loggers,
)
from rut_checker.infra.paths import resolve_output_path
from rut_checker.infra.settings import Settings
from rut_checker.io.exporters import ExportKind, ExportReport, OutputFormat, export_excel
from rut_checker.io.flat_exporters import export_csv, export_json
from rut_checker.io.readers import read_batch
from rut_checker.wiring import build_service

app = typer.Typer(
    name="rut-checker",
    help="Consulta del estado del RUT (DIAN) en modo asistido.",
    cls=SafeGroup,  # los errores de uso no repiten lo escrito (M-1)
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,  # Obs-3: un traceback con locales filtraría ids
)


@app.callback()
def _startup() -> None:
    """Consulta del estado del RUT (DIAN) en modo asistido."""
    force_utf8_output()
    silence_unconfigured_loggers()


# --- ejecución -----------------------------------------------------------------------------


HISTORY_WARNING: Final = (
    "Aviso: el número quedó en el historial del terminal; use `rut-checker consultar` "
    "sin argumento para ingresarlo sin eco."
)


FormatOption = Annotated[
    OutputFormat,
    typer.Option("--formato", help="Formato del resultado: xlsx (por defecto), csv o json."),
]


def _number_from_argument_or_prompt(number: str | None) -> str:
    """Número dado como argumento (con aviso de historial) o pedido por prompt sin eco."""
    if number is not None:
        echo_err(HISTORY_WARNING)
        return number
    if not stdin_is_tty():  # sin terminal el prompt sin eco se colgaría (getpass)
        fail("consultar sin número requiere una terminal interactiva.", EXIT_INPUT)
    return str(typer.prompt("Número de identificación", hide_input=True))


def _export(report: BatchReport, output_dir: Path, run_id: str, fmt: OutputFormat) -> ExportReport:
    """Despacha al exportador del formato pedido (xlsx por defecto)."""
    path = output_dir / f"resultado_{run_id}.{fmt.value}"
    outcomes = list(report.outcomes)
    match fmt:
        case OutputFormat.XLSX:
            return export_excel(outcomes, path, output_dir=output_dir)
        case OutputFormat.CSV:
            return export_csv(outcomes, path, output_dir=output_dir)
        case OutputFormat.JSON:
            return export_json(outcomes, path, output_dir=output_dir)


def _export_and_report(
    report: BatchReport,
    output_dir: Path,
    run_id: str,
    logger: logging.Logger,
    fmt: OutputFormat,
    *,
    single: bool,
) -> int:
    try:
        export = _export(report, output_dir, run_id, fmt)
    except ExportError:
        log_export_failed(logger, "EXPORT_FAILED", "ExportError")
        render_summary(report, None, run_id)
        raise
    if export.kind is ExportKind.JSON_BACKUP:
        log_export_failed(logger, "JSON_BACKUP", "ExportError")
    render_summary(report, export, run_id)
    if single:
        render_single_row(report)
    code = exit_code(report, export, single=single)
    if code == EXIT_INPUT:
        echo_err("El número no es válido: el motivo queda en la columna observacion del archivo.")
    return code


def _run(
    rows: list[InputRow],
    settings: Settings,
    destination: Path | None,
    fmt: OutputFormat,
    *,
    single: bool,
) -> int:
    check_output_extension(destination, fmt)
    clock = SystemClock()
    output_dir = resolve_output_path(destination, settings)
    run_id = new_run_id(clock)
    service = build_service(settings, run_id=run_id, output_dir=output_dir)
    # Idempotente por run_id: devuelve el mismo logger que usa el servicio.
    logger = configure_logging(run_id, settings.log_dir)
    try:
        announce_environment(
            settings, clock
        )  # tras validar la fuente: sin avisos de una config rechazada
        report = service.run(rows)
        return _export_and_report(report, output_dir, run_id, logger, fmt, single=single)
    except (*KNOWN_ERRORS, typer.Exit, typer.Abort):
        raise
    except Exception as error:  # el log recibe clase y sitios del traceback, nunca el mensaje
        log_exception(logger, error, "UNEXPECTED", with_trace=True)
        fail(unexpected_message(error, logged=True), EXIT_STOPPED)
    finally:
        close_run_logging(run_id)


@app.command(cls=SafeCommand)
def lote(
    file: Annotated[
        Path,
        typer.Argument(
            metavar="ARCHIVO", help="Archivo .xlsx o .csv con la columna identificacion."
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--salida", help="Subcarpeta de RUT_OUTPUT_DIR donde escribir el resultado."),
    ] = None,
    fmt: FormatOption = OutputFormat.XLSX,
) -> None:
    """Procesa un lote desde un archivo y escribe el resultado (Excel, CSV o JSON)."""
    with handled_errors():
        settings = load_settings()
        rows = read_batch(file, settings.max_batch_size)
        raise typer.Exit(_run(rows, settings, output, fmt, single=False))


@app.command(cls=SafeCommand)
def consultar(
    number: Annotated[
        str | None,
        typer.Argument(
            metavar="[NUMERO]",
            help="Cédula o NIT; si se omite se pide por prompt sin eco (no queda en el historial).",
        ),
    ] = None,
    check_digit: Annotated[
        str | None, typer.Option("--dv", help="Dígito de verificación del NIT.")
    ] = None,
    copy_date: Annotated[
        str | None, typer.Option("--fecha-copia", help="Fecha de la copia del RUT (AAAA-MM-DD).")
    ] = None,
    responsible: Annotated[
        str | None, typer.Option("--responsable", help="Usuario que validó la copia del RUT.")
    ] = None,
    fmt: FormatOption = OutputFormat.XLSX,
) -> None:
    """Consulta un único número (lote de una fila) y escribe el resultado."""
    with handled_errors():
        settings = load_settings()
        value = _number_from_argument_or_prompt(number)
        row = InputRow(
            row_index=0,
            raw_identification=value.strip(),
            raw_dv=check_digit,
            raw_copy_date=copy_date,
            raw_responsible=responsible,
        )
        raise typer.Exit(_run([row], settings, None, fmt, single=True))


@app.command(cls=SafeCommand)
def purgar(
    confirm: Annotated[
        bool, typer.Option("--confirmar", help="Elimina; sin esta opción solo lista conteos.")
    ] = False,
    source: Annotated[
        SourceKind | None,
        typer.Option("--fuente", help="Solo ejecuciones de esa fuente (p. ej. PORTAL_DIAN_C1)."),
    ] = None,
) -> None:
    """Lista (o elimina con --confirmar) los archivos vencidos de data/, output/ y logs/."""
    with handled_errors():
        settings = load_settings()
        raise typer.Exit(run_purge(settings, SystemClock(), confirm=confirm, source=source))
