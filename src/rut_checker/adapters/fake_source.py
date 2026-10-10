"""Fuente de pruebas y demostración (ADR-0002 §2). No toca la red ni el disco.

Decisiones de diseño:
- `kind = FAKE` y `paced = False` por defecto: no consulta ningún sistema externo, así que
  las pruebas no esperan el ritmo de RNF-02. `paced=True` es configurable para probar
  que el servicio aplica la pausa.
- Se programan fábricas y no instancias: relanzar la misma instancia acumularía `__traceback__`
  (con frames que contienen la identificación completa) y dejaría `__context__` pegado. Una
  instancia se rechaza con `TypeError`. El bloqueo de `fake` sin `RUT_ALLOW_FAKE` NO vive aquí:
  lo hace `build_service` (T-40).
- Respuesta por defecto (identificación no programada): `EXITOSA` con estado "ACTIVO" y
  nombre "PERSONA FICTICIA UNO", útil para demos con `RUT_SOURCE=fake`. Las pruebas que
  necesiten un fallo lo programan explícitamente.
- Una respuesta programada puede ser un `RutResult` (se devuelve), una fábrica de excepción de
  dominio (clase o callable sin argumentos; se crea una instancia NUEVA en cada llamada) o una
  secuencia de ambos (se consumen en orden, uno por llamada; cuando queda
  solo el último, se repite). Sirve para probar reintentos.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from rut_checker.domain.errors import RutCheckerError
from rut_checker.domain.models import IdentificationInput, RutResult
from rut_checker.domain.status import QueryStatus, SourceKind

type ErrorFactory = Callable[[], RutCheckerError]
type Response = RutResult | ErrorFactory
type Programmed = Response | Sequence[Response]

DEFAULT_RESULT = RutResult(
    status=QueryStatus.EXITOSA,
    source=SourceKind.FAKE,
    estado_rut="ACTIVO",
    name="PERSONA FICTICIA UNO",
    observation="Resultado ficticio de pruebas; no válido",
)


class FakeSource:
    """Implementación programable de `RutSourcePort` para pruebas y demostraciones."""

    def __init__(
        self,
        responses: Mapping[str, Programmed] | None = None,
        *,
        default: Response = DEFAULT_RESULT,
        paced: bool = False,
    ) -> None:
        """Crea la fuente.

        Args:
            responses: Respuestas programadas por número de identificación (sin DV).
            default: Respuesta para identificaciones no programadas.
            paced: Si aplica el ritmo entre consultas (RNF-02).

        Raises:
            ValueError: Si alguna secuencia programada está vacía.
            TypeError: Si se pasa una instancia de excepción en lugar de una fábrica.
        """
        self._paced = paced
        _check_response(default)
        self._default = default
        self._queues: dict[str, list[Response]] = {}
        for identification, programmed in (responses or {}).items():
            self.program(identification, programmed)
        self._calls: Counter[str] = Counter()
        self.close_count = 0

    @property
    def kind(self) -> SourceKind:
        """Origen del dato: siempre `FAKE`."""
        return SourceKind.FAKE

    @property
    def paced(self) -> bool:
        """Si aplica el ritmo entre consultas (RNF-02)."""
        return self._paced

    def program(self, identification: str, programmed: Programmed) -> None:
        """Programa (o reemplaza) la respuesta de una identificación."""
        queue = list(programmed) if isinstance(programmed, Sequence) else [programmed]
        for response in queue:
            _check_response(response)
        if not queue:
            raise ValueError("la secuencia de respuestas programadas no puede estar vacía")
        self._queues[identification] = queue

    def query(self, ident: IdentificationInput) -> RutResult:
        """Devuelve o lanza la respuesta programada; cuenta la llamada."""
        self._calls[ident.identification] += 1
        response = self._next_response(ident.identification)
        if isinstance(response, RutResult):
            return response
        raise response()

    def _next_response(self, identification: str) -> Response:
        queue = self._queues.get(identification)
        if queue is None:
            return self._default
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def close(self) -> None:
        """Idempotente: solo registra cuántas veces se invocó."""
        self.close_count += 1

    def calls_for(self, identification: str) -> int:
        """Número de consultas recibidas para una identificación."""
        return self._calls[identification]

    @property
    def total_calls(self) -> int:
        """Número total de consultas recibidas."""
        return self._calls.total()


def _check_response(response: object) -> None:
    if isinstance(response, BaseException) or not (
        isinstance(response, RutResult) or callable(response)
    ):
        raise TypeError("la respuesta debe ser un RutResult o una fábrica de excepción (clase)")
