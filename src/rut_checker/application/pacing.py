"""Ritmo responsable entre llamadas a una fuente externa (RNF-02)."""

from rut_checker.application.clock import Sleeper


class Pacer:
    """Espera `max(pausa mínima, backoff)` antes de cada llamada a una fuente con ritmo.

    También antes de la primera de la ejecución: protege invocaciones repetidas del CLI, cada una
    con su propio `Pacer` (L-3, revisión de seguridad de T-35).
    """

    def __init__(self, sleeper: Sleeper, min_delay_s: float) -> None:
        self._sleeper = sleeper
        self._min_delay_s = min_delay_s

    def before_call(self, paced: bool, retry_delay_s: float = 0.0) -> None:
        """Espera lo que corresponda antes de llamar a una fuente.

        Args:
            paced: `RutSourcePort.paced` de la fuente; si es `False` solo se respeta el backoff.
            retry_delay_s: Espera pedida por la política de reintentos (0 si no es reintento).
        """
        wait = max(retry_delay_s, self._min_delay_s) if paced else retry_delay_s
        if wait > 0:
            self._sleeper.sleep(wait)
