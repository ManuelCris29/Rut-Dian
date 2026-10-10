"""Fábrica del adaptador del portal (T-40; la implementa T-49 cuando T-14 se desbloquee).

`build_service` la importa de forma perezosa y solo tras `ensure_portal_enabled`, de modo que
ni Playwright ni el navegador se tocan salvo con la triple llave completa. Mientras
`DianPortalSource` no exista (T-48/T-49, bloqueadas por T-14) la fábrica falla de forma segura:
nunca degrada en silencio a otra fuente (ADR-0002 §3).
"""

from rut_checker.adapters.dian_portal.selectors import EnabledPortal
from rut_checker.domain.errors import SourceNotEnabledError, SourceNotEnabledReason
from rut_checker.infra.settings import Settings
from rut_checker.ports.clock import Clock
from rut_checker.ports.operator import OperatorPort
from rut_checker.ports.rut_source import RutSourcePort


def create_portal_source(
    enabled: EnabledPortal, settings: Settings, operator: OperatorPort, clock: Clock
) -> RutSourcePort:
    """Crea `DianPortalSource` a partir de la puerta única `EnabledPortal`.

    Raises:
        SourceNotEnabledError: motivo `PORTAL_ADAPTER_PENDING` hasta que exista el adaptador.
    """
    raise SourceNotEnabledError(SourceNotEnabledReason.PORTAL_ADAPTER_PENDING)
