"""CLI de `rut-checker` (ARQUITECTURA §6) y cableado manual de dependencias (`build_service`).

Comandos: `lote <archivo> [--salida DIR]`, `consultar [NUMERO] [--dv ...]` y `purgar`
(lógica en `cli_purge.py`). Códigos de salida:
0 completo, 1 lote detenido (o fallo inesperado), 2 entrada/configuración/ruta, 3 exportación.

Decisiones:
- `build_service` es el único lugar de cableado (DI manual). Valida la fuente ANTES de crear
  carpetas o archivos: una configuración rechazada (portal deshabilitado, `fake` sin permiso)
  no deja logs ni salidas y no abre navegador ni red (G11).
- El respaldo es siempre `DocumentCopySource(ContingencySource())`, también con `contingency`
  y `fake`: tras una parada, las filas con copia vigente se siguen validando contra la copia y
  solo el resto queda pendiente (ADR-0002 §3/§4; el dedupe de T-45 ya distingue la fuente que
  resolvió cada fila). Primaria y respaldo son instancias distintas.
- El adaptador del portal se importa de forma perezosa y solo tras `ensure_portal_enabled`:
  en modo `contingency`/`fake` no se importan ni `playwright` ni `yaml`.
- El número del comando `consultar` se pide por prompt sin eco (Obs-11, evita el historial).
"""

import logging
from pathlib import Path
from typing import Annotated, Final, assert_never

import typer

from rut_checker.adapters.console_operator import ConsoleOperator, stdin_is_tty
from rut_checker.adapters.contingency_source import ContingencySource
from rut_checker.adapters.document_copy_source import DocumentCopySource
from rut_checker.adapters.fake_source import FakeSource
from rut_checker.application.batch_service import BatchQueryService
from rut_checker.application.clock import SystemClock, SystemSleeper
from rut_checker.application.report import BatchReport
from rut_checker.application.retry_policy import BackoffRetryPolicy
from rut_checker.cli_purge import run_purge
from rut_checker.cli_support import (
    EXIT_INPUT,
    EXIT_STOPPED,
    KNOWN_ERRORS,
    SafeCommand,
    SafeGroup,
    announce_environment,
    echo_err,
    exit_code,
    fail,
    force_utf8_output,
    handled_errors,
    load_settings,
    new_run_id,
    prepare_run_dirs,
    render_single_row,
    render_summary,
    unexpected_message,
)
from rut_checker.domain.errors import ExportError, FakeNotAllowedError
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
from rut_checker.io.exporters import ExportKind, export_excel
from rut_checker.io.readers import read_batch
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort

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


# --- cableado ------------------------------------------------------------------------------


def _copy_source(clock: Clock) -> RutSourcePort:
    return DocumentCopySource(ContingencySource(), clock)


def _portal_source(settings: Settings, operator: OperatorPort, clock: Clock) -> RutSourcePort:
    """Triple llave y adaptador del portal (import perezoso: nada de Playwright/yaml antes)."""
    from rut_checker.adapters.dian_portal.factory import create_portal_source
    from rut_checker.adapters.dian_portal.location import project_root
    from rut_checker.adapters.dian_portal.selectors import ensure_portal_enabled

    if (
        not settings.selectors_path.is_absolute()
    ):  # I-3: la ruta relativa es de la raíz del proyecto
        resolved = project_root() / settings.selectors_path
        settings = settings.model_copy(update={"selectors_path": resolved})
    enabled = ensure_portal_enabled(settings)
    return create_portal_source(enabled, settings, operator, clock)


def _primary_source(settings: Settings, operator: OperatorPort, clock: Clock) -> RutSourcePort:
    match settings.source:
        case "contingency":
            return _copy_source(clock)
        case "fake":
            if not settings.allow_fake:
                raise FakeNotAllowedError
            return FakeSource()
        case "dian_portal":
            return _portal_source(settings, operator, clock)
        case unreachable:
            assert_never(unreachable)


def build_service(
    settings: Settings, *, run_id: str | None = None, output_dir: Path | None = None
) -> BatchQueryService:
    """Cablea el servicio de lotes según `settings.source` (DI manual).

    Valida la fuente, luego las carpetas, y por último configura el logger de la ejecución. El
    llamador que pase `run_id` debe cerrar el logger con `close_run_logging(run_id)`.

    Args:
        settings: Configuración ya validada.
        run_id: Identificador de la ejecución; si no se da se genera uno.
        output_dir: Carpeta de salida efectiva (`--salida`); por defecto `RUT_OUTPUT_DIR`.

    Raises:
        SourceNotEnabledError: portal sin habilitar o adaptador pendiente.
        SelectorsNotValidatedError: `selectors.yaml` sin validar.
        FakeNotAllowedError: `fake` sin `RUT_ALLOW_FAKE`.
        UnsafePathError: carpetas de datos, logs o salida no permitidas.
    """
    clock = SystemClock()
    operator = ConsoleOperator()
    primary = _primary_source(settings, operator, clock)
    try:
        prepare_run_dirs(settings, output_dir)
        logger = configure_logging(run_id or new_run_id(clock), settings.log_dir)
    except Exception:
        primary.close()
        raise
    return BatchQueryService(
        primary,
        _copy_source(clock),
        operator,
        clock,
        SystemSleeper(),
        settings,
        logger,
        BackoffRetryPolicy.from_settings(settings),
    )


# --- ejecución -----------------------------------------------------------------------------


HISTORY_WARNING: Final = (
    "Aviso: el número quedó en el historial del terminal; use `rut-checker consultar` "
    "sin argumento para ingresarlo sin eco."
)


def _number_from_argument_or_prompt(number: str | None) -> str:
    """Número dado como argumento (con aviso de historial) o pedido por prompt sin eco."""
    if number is not None:
        echo_err(HISTORY_WARNING)
        return number
    if not stdin_is_tty():  # sin terminal el prompt sin eco se colgaría (getpass)
        fail("consultar sin número requiere una terminal interactiva.", EXIT_INPUT)
    return str(typer.prompt("Número de identificación", hide_input=True))


def _export_and_report(
    report: BatchReport, output_dir: Path, run_id: str, logger: logging.Logger, *, single: bool
) -> int:
    path = output_dir / f"resultado_{run_id}.xlsx"
    try:
        export = export_excel(list(report.outcomes), path, output_dir=output_dir)
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
        echo_err("El número no es válido: el motivo queda en la columna observacion del Excel.")
    return code


def _run(
    rows: list[InputRow], settings: Settings, destination: Path | None, *, single: bool
) -> int:
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
        return _export_and_report(report, output_dir, run_id, logger, single=single)
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
        typer.Option("--salida", help="Subcarpeta de RUT_OUTPUT_DIR donde escribir el Excel."),
    ] = None,
) -> None:
    """Procesa un lote desde un archivo y escribe el Excel de resultados."""
    with handled_errors():
        settings = load_settings()
        rows = read_batch(file, settings.max_batch_size)
        raise typer.Exit(_run(rows, settings, output, single=False))


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
) -> None:
    """Consulta un único número (lote de una fila) y escribe el Excel."""
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
        raise typer.Exit(_run([row], settings, None, single=True))


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
