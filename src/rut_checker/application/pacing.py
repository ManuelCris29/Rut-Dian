"""Ritmo responsable entre llamadas a una fuente externa (RNF-02)."""

from rut_checker.application.clock import Sleeper


class Pacer:
    """Espera `max(pausa mínima, backoff)` antes de cada llamada, salvo antes de la primera."""

    def __init__(self, sleeper: Sleeper, min_delay_s: float) -> None:
        self._sleeper = sleeper
        self._min_delay_s = min_delay_s
        self._paced_calls = 0

    def before_call(self, paced: bool, retry_delay_s: float = 0.0) -> None:
        """Espera lo que corresponda antes de llamar a una fuente.

        Args:
            paced: `RutSourcePort.paced` de la fuente; si es `False` solo se respeta el backoff.
            retry_delay_s: Espera pedida por la política de reintentos (0 si no es reintento).
        """
        wait = retry_delay_s
        if paced:
            if self._paced_calls > 0:
                wait = max(wait, self._min_delay_s)
            self._paced_calls += 1
        if wait > 0:
            self._sleeper.sleep(wait)
