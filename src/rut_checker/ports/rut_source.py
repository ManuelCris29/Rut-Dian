"""Puerto de fuente de datos del RUT (ADR-0002 §1). Sin lógica: solo el contrato."""

from typing import Protocol, runtime_checkable

from rut_checker.domain.models import IdentificationInput, RutResult
from rut_checker.domain.status import SourceKind


@runtime_checkable
class RutSourcePort(Protocol):
    """Fuente intercambiable de resultados (portal, copia del RUT, contingencia, pruebas).

    `runtime_checkable` es una verificación superficial (solo comprueba que existan los
    miembros, no sus firmas ni tipos): el contrato lo garantiza mypy. `kind` y `paced` son
    propiedades de solo lectura, de modo que un adaptador puede implementarlas como
    `property`, `ClassVar` o `Final`.
    """

    @property
    def kind(self) -> SourceKind:
        """Identifica al adaptador (p. ej. `run_started`, `purgar --fuente`).

        La columna `fuente` de la salida sale siempre de `RutResult.source`, no de aquí.
        """
        ...

    @property
    def paced(self) -> bool:
        """`True` si consulta un sistema externo y por tanto aplica el ritmo (RNF-02)."""
        ...

    def query(self, ident: IdentificationInput) -> RutResult:
        """Devuelve un resultado de negocio o lanza una `RutCheckerError`.

        Nunca devuelve datos vacíos silenciosos (RNF-07) ni traduce excepciones a
        `QueryStatus`: eso lo hace únicamente `BatchQueryService`.
        """
        ...

    def close(self) -> None:
        """Libera recursos (p. ej. el navegador). Debe ser idempotente."""
        ...
