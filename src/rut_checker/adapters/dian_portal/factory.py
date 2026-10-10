"""Fábrica del adaptador del portal (T-40, T-49).

`build_service` la importa de forma perezosa y solo tras `ensure_portal_enabled`, de modo que
ni Playwright ni el navegador se tocan salvo con la triple llave completa. `DianPortalSource`
vuelve a exigir el token `EnabledPortal` y falla de forma segura (`SourceNotEnabledError`) si no
lo recibe: nunca degrada en silencio a otra fuente (ADR-0002 §3).
"""

from rut_checker.adapters.dian_portal.selectors import EnabledPortal
from rut_checker.adapters.dian_portal.source import ChallengeSink, DianPortalSource
from rut_checker.infra.settings import Settings
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort


def create_portal_source(
    enabled: EnabledPortal,
    settings: Settings,
    operator: OperatorPort,
    clock: Clock,
    on_challenge: ChallengeSink | None = None,
) -> RutSourcePort:
    """Crea `DianPortalSource` (navegador visible) a partir de la puerta única `EnabledPortal`.

    Raises:
        SourceNotEnabledError: si `enabled` no es un `EnabledPortal` o la URL no está permitida.
        PortalUnavailable: si el navegador no pudo abrirse.
    """
    return DianPortalSource(enabled, settings, operator, on_challenge=on_challenge)
