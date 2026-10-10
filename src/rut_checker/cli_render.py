"""Salida a consola de la CLI (T-40/T-47): resumen, fila única y código de salida.

Nunca incluye una identificación completa, un valor de configuración ni texto de excepciones.
"""

from pathlib import Path
from typing import Final

import typer

from rut_checker.application.report import BatchReport
from rut_checker.application.row_results import masked_id
from rut_checker.cli_support import EXIT_EXPORT, EXIT_INPUT, EXIT_OK, EXIT_STOPPED, echo_err, fail
from rut_checker.domain.status import QueryStatus
from rut_checker.io.exporters import ExportKind, ExportReport, OutputFormat

_ALTERNATIVE_KINDS: Final = frozenset(
    {ExportKind.XLSX_ALTERNATIVE, ExportKind.CSV_ALTERNATIVE, ExportKind.JSON_ALTERNATIVE}
)
_KIND_LABELS: Final = {
    ExportKind.XLSX: "Excel",
    ExportKind.CSV: "CSV",
    ExportKind.JSON: "JSON",
}


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
            f"No se pudo escribir el archivo solicitado: se guardó un respaldo JSON en "
            f"{export.path}. Revise que el archivo no esté abierto."
        )
    elif export.kind in _ALTERNATIVE_KINDS:
        typer.echo(f"El archivo previsto estaba en uso; resultado escrito en {export.path}")
    else:
        typer.echo(f"{_KIND_LABELS[export.kind]}: {export.path}")


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


def check_output_extension(destination: Path | None, fmt: OutputFormat) -> None:
    """Código 2 si `--salida` trae una extensión de salida distinta del `--formato`."""
    if destination is None:
        return
    suffix = destination.suffix.lower().removeprefix(".")
    if suffix in {item.value for item in OutputFormat} and suffix != fmt.value:
        fail("La extensión de --salida no concuerda con --formato.", EXIT_INPUT)
