"""Cableado manual de dependencias (`build_service`), separado de la CLI (DI manual).

Decisiones:
- `build_service` es el único lugar de cableado. Valida la fuente ANTES de crear carpetas o
  archivos: una configuración rechazada (portal deshabilitado, `fake` sin permiso) no deja logs
  ni salidas y no abre navegador ni red (G11).
- El respaldo es siempre `DocumentCopySource(ContingencySource())`, también con `contingency`
  y `fake`: tras una parada, las filas con copia vigente se siguen validando contra la copia y
  solo el resto queda pendiente (ADR-0002 §3/§4; el dedupe de T-45 ya distingue la fuente que
  resolvió cada fila). Primaria y respaldo son instancias distintas.
- El adaptador del portal se importa de forma perezosa y solo tras `ensure_portal_enabled`:
  en modo `contingency`/`fake` no se importan ni `playwright` ni `yaml`.
"""

from pathlib import Path
from typing import assert_never

from rut_checker.adapters.console_operator import ConsoleOperator
from rut_checker.adapters.contingency_source import ContingencySource
from rut_checker.adapters.document_copy_source import DocumentCopySource
from rut_checker.adapters.fake_source import FakeSource
from rut_checker.application.batch_service import BatchQueryService
from rut_checker.application.clock import SystemClock, SystemSleeper
from rut_checker.application.retry_policy import BackoffRetryPolicy
from rut_checker.cli_support import new_run_id, prepare_run_dirs
from rut_checker.domain.errors import FakeNotAllowedError
from rut_checker.infra.logging import ChallengeLogSink, configure_logging
from rut_checker.infra.settings import Settings
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort


def _copy_source(clock: Clock) -> RutSourcePort:
    return DocumentCopySource(ContingencySource(), clock)


def _portal_source(
    settings: Settings, operator: OperatorPort, clock: Clock, sink: ChallengeLogSink
) -> RutSourcePort:
    """Triple llave y adaptador del portal (import perezoso: nada de Playwright/yaml antes)."""
    from rut_checker.adapters.dian_portal.factory import create_portal_source
    from rut_checker.adapters.dian_portal.location import project_root
    from rut_checker.adapters.dian_portal.selectors import ensure_portal_enabled

    if not settings.selectors_path.is_absolute():  # I-3: ruta relativa = raíz del proyecto
        resolved = project_root() / settings.selectors_path
        settings = settings.model_copy(update={"selectors_path": resolved})
    enabled = ensure_portal_enabled(settings)
    return create_portal_source(enabled, settings, operator, clock, sink)


def _primary_source(
    settings: Settings, operator: OperatorPort, clock: Clock, sink: ChallengeLogSink
) -> RutSourcePort:
    match settings.source:
        case "contingency":
            return _copy_source(clock)
        case "fake":
            if not settings.allow_fake:
                raise FakeNotAllowedError
            return FakeSource()
        case "dian_portal":
            return _portal_source(settings, operator, clock, sink)
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
        SourceNotEnabledError: portal sin habilitar o URL no permitida.
        SelectorsNotValidatedError: `selectors.yaml` sin validar.
        FakeNotAllowedError: `fake` sin `RUT_ALLOW_FAKE`.
        UnsafePathError: carpetas de datos, logs o salida no permitidas.
    """
    clock = SystemClock()
    operator = ConsoleOperator()
    sink = ChallengeLogSink()  # el logger se enlaza después de validar las carpetas
    primary = _primary_source(settings, operator, clock, sink)
    try:
        prepare_run_dirs(settings, output_dir)
        logger = configure_logging(run_id or new_run_id(clock), settings.log_dir)
        sink.bind(logger)
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
