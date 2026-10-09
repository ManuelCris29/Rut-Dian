"""Catálogos de estado de consulta y fuente de datos.

`QueryStatus` replica el catálogo de `specs/excepciones.md` (sin `ERROR_ALMACENAMIENTO`,
que no se implementa porque no hay base de datos). La traducción excepción -> estado
vive únicamente en `BatchQueryService`.
"""

from enum import StrEnum


class QueryStatus(StrEnum):
    """Estado final de una consulta; cada fila termina en exactamente uno."""

    EXITOSA = "EXITOSA"
    SIN_RESULTADOS = "SIN_RESULTADOS"
    ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
    PORTAL_NO_DISPONIBLE = "PORTAL_NO_DISPONIBLE"
    TIEMPO_AGOTADO = "TIEMPO_AGOTADO"
    ESTRUCTURA_CAMBIADA = "ESTRUCTURA_CAMBIADA"
    RESULTADO_INCOMPLETO = "RESULTADO_INCOMPLETO"
    SESION_VENCIDA = "SESION_VENCIDA"
    REQUIERE_INTERVENCION_HUMANA = "REQUIERE_INTERVENCION_HUMANA"
    PENDIENTE_VALIDACION_MANUAL = "PENDIENTE_VALIDACION_MANUAL"
    VALIDADA_COPIA_RUT = "VALIDADA_COPIA_RUT"
    ERROR_EXPORTACION = "ERROR_EXPORTACION"


class SourceKind(StrEnum):
    """Origen del dato (columna `fuente` de la salida, RNF-04)."""

    PORTAL_DIAN_C1 = "PORTAL_DIAN_C1"
    COPIA_RUT_TERCERO = "COPIA_RUT_TERCERO"
    CONTINGENCIA_MANUAL = "CONTINGENCIA_MANUAL"
    SIN_CONSULTA = "SIN_CONSULTA"
    FAKE = "FAKE"
