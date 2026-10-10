"""Dedupe de filas de un lote (RF-11, RNF-02).

La clave depende de quién resuelve la fila:
- Consulta real a una fuente primaria con `paced` (externa): solo la identificación, porque copia
  y nota no cambian lo que devuelve el portal y cada consulta extra pesa sobre la DIAN.
- Fuente primaria local, o fila resuelta por el respaldo (parada, circuito o `PortalUnavailable`
  agotado): `(identificación, evidencia de copia, nota con espacios colapsados)`, porque el
  respaldo sí depende de la copia y de la nota.
Tras una parada solo se reutiliza un resultado previo de la primaria si fue `EXITOSA` o
`SIN_RESULTADOS`; cualquier otro (error, pendiente) se vuelve a resolver con el respaldo.
"""

from typing import Final

from rut_checker.domain.models import CopyEvidence, IdentificationInput, RutResult
from rut_checker.domain.status import QueryStatus

type _Key = tuple[str, CopyEvidence | None, str | None]

_REUSABLE_AFTER_STOP: Final = frozenset({QueryStatus.EXITOSA, QueryStatus.SIN_RESULTADOS})


def _full_key(ident: IdentificationInput) -> _Key:
    note = " ".join(ident.note.split()) if ident.note else None
    return (ident.identification, ident.copy_evidence, note)


class DedupeCache:
    """Caché de resultados de una ejecución."""

    def __init__(self, primary_paced: bool) -> None:
        self._primary_paced = primary_paced
        self._primary: dict[_Key, RutResult] = {}
        self._fallback: dict[_Key, RutResult] = {}

    def _primary_key(self, ident: IdentificationInput) -> _Key:
        if self._primary_paced:
            return (ident.identification, None, None)
        return _full_key(ident)

    def lookup(self, ident: IdentificationInput, *, stopped: bool) -> RutResult | None:
        """Resultado ya obtenido para una fila equivalente, o `None`.

        Args:
            ident: Identificación de la fila.
            stopped: Si el lote ya se detuvo (la fila la resolvería el respaldo).
        """
        cached = self._primary.get(self._primary_key(ident))
        if cached is not None and (not stopped or cached.status in _REUSABLE_AFTER_STOP):
            return cached
        return self._fallback.get(_full_key(ident)) if stopped else None

    def store(self, ident: IdentificationInput, result: RutResult, *, by_fallback: bool) -> None:
        """Guarda el resultado en la tabla de quien resolvió la fila."""
        if by_fallback:
            self._fallback[_full_key(ident)] = result
        else:
            self._primary[self._primary_key(ident)] = result
