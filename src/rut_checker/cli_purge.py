"""Comando `purgar` (T-44, ARQUITECTURA §6 y §11): simulación por defecto, borrado con --confirmar.

Decisiones:
- Sin `--confirmar` solo se muestran conteos por `<carpeta>.<tipo>`: nunca nombres de archivo,
  `run_id` ni contenido.
- Con `--fuente` se eligen las ejecuciones de esa fuente SIN importar la edad (es una depuración
  ordenada por una respuesta contraria de la DIAN, INFORME §9); sin ella, la edad de
  `Settings.retention_days` (30 días para snapshots; ver `infra/retention.py`).
- Las carpetas se validan (`assert_safe_dir`) y no pueden ser enlaces antes de listar o borrar.
- El evento `purge_executed` se escribe en un log de mantenimiento propio (`run_<run_id>.jsonl`
  nuevo) DESPUÉS de borrar, así que la misma purga nunca lo elimina. Los conteos por carpeta y
  tipo son los de los archivos seleccionados; `deleted` y `failed` son el resultado real.
- Los fallos de borrado solo se cuentan (sin rutas); una purga parcial avisa por stderr y sale 1.
- Con `--fuente`, los archivos de ejecuciones sin log de fuente legible no se borran: se cuentan
  (`unknown_source`) y se muestran para revisión manual.
- Con `retention_days` < 365 se avisa de que es menor que la exigida por RN-06.
"""

from pathlib import Path
from typing import Final

import typer

from rut_checker.cli_support import EXIT_OK, EXIT_STOPPED, echo_err, new_run_id
from rut_checker.domain.errors import UnsafePathError, UnsafePathReason
from rut_checker.domain.status import SourceKind
from rut_checker.infra.logging import close_run_logging, configure_logging, log_purge_executed
from rut_checker.infra.paths import assert_safe_dir, ensure_private_dir
from rut_checker.infra.purge_keys import TOTAL_DELETED, TOTAL_FAILED, UNKNOWN_SOURCE, Folder
from rut_checker.infra.retention import count_by_bucket, plan_purge, purge
from rut_checker.infra.settings import Settings
from rut_checker.ports.clock import Clock

EXIT_PARTIAL: Final = EXIT_STOPPED  # 1: purga incompleta (algún archivo no se pudo eliminar)
RN06_RETENTION_DAYS: Final = 365


def _roots(settings: Settings) -> list[tuple[Folder, Path]]:
    """Carpetas de trabajo validadas: seguras y que no sean enlaces simbólicos/junctions."""
    roots = [
        (Folder.DATA, settings.data_dir),
        (Folder.OUTPUT, settings.output_dir),
        (Folder.LOGS, settings.log_dir),
    ]
    for _, path in roots:
        assert_safe_dir(path)
        if path.is_symlink() or path.is_junction():
            raise UnsafePathError(UnsafePathReason.INVALID_PATH)
    return roots


def _log_maintenance(
    settings: Settings, clock: Clock, counts: dict[str, int], source: SourceKind | None
) -> None:
    """Escribe `purge_executed` en un log propio de la ejecución de mantenimiento."""
    ensure_private_dir(settings.log_dir)
    run_id = new_run_id(clock)
    logger = configure_logging(run_id, settings.log_dir)
    try:
        log_purge_executed(logger, counts, source)
    finally:
        close_run_logging(run_id)


def _echo_counts(counts: dict[str, int], total: int) -> None:
    for key, count in counts.items():
        typer.echo(f"  {key}: {count}")
    typer.echo(f"Total: {total} archivos.")


def run_purge(settings: Settings, clock: Clock, *, confirm: bool, source: SourceKind | None) -> int:
    """Lista o elimina lo vencido (o lo de una fuente) en `data/`, `output/` y `logs/`.

    Returns:
        0 sin fallos, 1 si algún archivo no se pudo eliminar.

    Raises:
        UnsafePathError: alguna carpeta es insegura o es un enlace (la CLI sale con código 2).
    """
    roots = _roots(settings)
    paths = [path for _, path in roots]
    if settings.retention_days < RN06_RETENTION_DAYS:
        echo_err("Aviso: la retención configurada es menor que la exigida por RN-06 (365 días).")
    plan = plan_purge(
        paths,
        clock.now(),
        source,
        max_age_days=settings.retention_days,
        source_excluded=[settings.data_dir],
    )
    counts = count_by_bucket(plan.selected, roots)
    unknown = len(plan.unknown_source)
    if unknown:
        counts[UNKNOWN_SOURCE] = unknown
    if not confirm:
        typer.echo("Simulación: no se eliminó nada. Use --confirmar para eliminar.")
    _echo_counts({k: v for k, v in counts.items() if k != UNKNOWN_SOURCE}, len(plan.selected))
    if unknown:
        typer.echo(f"{unknown} archivos de ejecuciones sin log de fuente: revise manualmente.")
    if not confirm:
        return EXIT_OK
    result = purge(plan.selected, within=paths)
    typer.echo(f"Eliminados: {result.deleted}.")
    if result.failed:
        echo_err(f"No se pudieron eliminar {result.failed} archivos (en uso o sin permiso).")
    totals = {TOTAL_DELETED: result.deleted, TOTAL_FAILED: result.failed}
    _log_maintenance(settings, clock, {**counts, **totals}, source)
    return EXIT_PARTIAL if result.failed else EXIT_OK
