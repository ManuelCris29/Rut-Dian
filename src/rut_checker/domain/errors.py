# ruff: noqa: N818  (nombres sin sufijo Error fijados por docs/ARQUITECTURA.md §7)
"""Excepciones de dominio con mensajes genéricos.

Ninguna incluye el número de identificación, el valor crudo ni el texto de
excepciones de terceros (ARQUITECTURA §7). La traducción a `QueryStatus` NO vive
aquí: la hace únicamente `BatchQueryService`.
"""

from enum import StrEnum


class RutCheckerError(Exception):
    """Base de todas las excepciones del dominio."""

    default_message = "Error en la consulta del RUT"

    def __init__(self) -> None:
        super().__init__(self._message())

    def _message(self) -> str:
        """Mensaje genérico de la excepción (sin datos personales)."""
        return self.default_message


class InvalidReason(StrEnum):
    """Conjunto cerrado de motivos de entrada inválida.

    Se usa un conjunto cerrado (y no texto libre) para que sea imposible que el
    valor crudo de la identificación llegue al mensaje de la excepción.
    """

    EMPTY = "vacío"
    NON_NUMERIC = "contiene caracteres no numéricos"
    LENGTH_OUT_OF_RANGE = "longitud fuera de rango"
    BAD_CHECK_DIGIT = "DV incorrecto"
    UNREADABLE_COPY_DATE = "fecha de copia del RUT ilegible"
    INVALID_RESPONSIBLE = "responsable de validación inválido"
    OBSERVATION_TOO_LONG = "observación demasiado larga"


class InvalidIdentification(RutCheckerError):
    """La entrada no cumple las reglas de formato; la fuente no se invoca."""

    def __init__(self, reason: InvalidReason) -> None:
        if not isinstance(reason, InvalidReason):
            raise TypeError("motivo de entrada inválida fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        return f"Número inválido: {self.reason.value}"


class PortalUnavailable(RutCheckerError):
    """Mantenimiento, error 5xx o fallo de red en el canal."""

    default_message = "El servicio de la DIAN no está disponible"


class QueryTimeout(RutCheckerError):
    """Se agotó el tiempo de navegación o de espera del resultado."""

    default_message = "Se agotó el tiempo de espera"


class SessionExpired(RutCheckerError):
    """El canal reinició la sesión o la vista."""

    default_message = "La sesión expiró"


class StructureChanged(RutCheckerError):
    """Falta un elemento obligatorio: el portal cambió."""

    default_message = "El portal cambió; se requiere mantenimiento"


class IncompleteResult(RutCheckerError):
    """Faltan campos obligatorios en el resultado."""

    default_message = "Resultado incompleto"


class HumanInterventionRequired(RutCheckerError):
    """Desafío de seguridad que debe resolver una persona."""

    default_message = "Se requiere verificación humana"


class AccessBlocked(RutCheckerError):
    """El canal bloqueó el acceso."""

    default_message = "El acceso fue bloqueado; se requiere verificación humana"


class ExportError(RutCheckerError):
    """Falla al escribir el archivo de salida."""

    default_message = "No se pudo exportar el resultado"


class SourceNotEnabledError(RutCheckerError):
    """La fuente solicitada no está habilitada por configuración."""

    default_message = "La fuente solicitada no está habilitada"


class SelectorsNotValidatedError(RutCheckerError):
    """Los selectores del portal no han sido validados contra un snapshot real."""

    default_message = "Los selectores del portal no están validados"


class FakeNotAllowedError(RutCheckerError):
    """La fuente de pruebas no está permitida en este entorno."""

    default_message = "La fuente de pruebas no está permitida"
