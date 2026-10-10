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
    RESPONSIBLE_WITHOUT_COPY_DATE = "responsable sin fecha de copia"


class InvalidIdentification(RutCheckerError):
    """La entrada no cumple las reglas de formato; la fuente no se invoca."""

    def __init__(self, reason: InvalidReason) -> None:
        if not isinstance(reason, InvalidReason):
            raise TypeError("motivo de entrada inválida fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        return f"Número inválido: {self.reason.value}"


class InvalidFileReason(StrEnum):
    """Conjunto cerrado de motivos por los que un archivo de entrada no se procesa.

    Sin texto libre: imposibles de contaminar con rutas, valores de celdas o texto de librerías.
    """

    UNSUPPORTED_FORMAT = "formato no soportado"
    TOO_LARGE = "archivo demasiado grande"
    UNREADABLE = "archivo ilegible"
    NOT_UTF8 = "codificación de texto no soportada"
    MISSING_ID_COLUMN = "falta la columna identificacion"
    DUPLICATE_COLUMN = "columna duplicada en el encabezado"
    FIRST_SHEET_HIDDEN = "la primera hoja está oculta"
    TOO_MANY_ROWS = "el lote supera el máximo de filas"
    TOO_MANY_RAW_ROWS = "demasiadas filas vacías o con formato"
    EMPTY = "archivo vacío"


class InvalidInputFile(RutCheckerError):
    """El archivo de entrada no se puede procesar (formato, columnas o tamaño del lote).

    La CLI lo traduce al código de salida 2 (ARQUITECTURA §5.2 y §6).
    """

    def __init__(self, reason: InvalidFileReason) -> None:
        if not isinstance(reason, InvalidFileReason):
            raise TypeError("motivo de archivo inválido fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        return f"Archivo de entrada inválido: {self.reason.value}"


class UnsafePathReason(StrEnum):
    """Conjunto cerrado de motivos por los que una ruta de salida o carpeta se rechaza."""

    OUTSIDE_OUTPUT_DIR = "la ruta queda fuera de la carpeta de salida"
    INSIDE_GIT_TREE = "la carpeta está dentro de un árbol git"
    INVALID_PATH = "ruta inválida"


class UnsafePathError(RutCheckerError):
    """Ruta de salida o carpeta de trabajo insegura (sin incluir la ruta en el mensaje).

    La CLI la traduce al código de salida 2 (ARQUITECTURA §6).
    """

    def __init__(self, reason: UnsafePathReason) -> None:
        if not isinstance(reason, UnsafePathReason):
            raise TypeError("motivo de ruta insegura fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        return f"Ruta no permitida: {self.reason.value}"


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


class SourceNotEnabledReason(StrEnum):
    """Conjunto cerrado de motivos por los que el portal no está habilitado (llaves 1 y 2)."""

    FLAG_DISABLED = "la fuente dian_portal está deshabilitada"
    MISSING_APPROVAL_REF = "falta una referencia de aprobación válida"
    INVALID_URL = "la URL del portal no es válida"
    HEADLESS_NOT_ALLOWED = "el navegador del portal debe ser visible"


class SourceNotEnabledError(RutCheckerError):
    """La fuente solicitada no está habilitada por configuración.

    Sin motivo (`reason=None`) usa el mensaje genérico; con motivo, lo añade sin valores de
    configuración.
    """

    default_message = "La fuente solicitada no está habilitada"

    def __init__(self, reason: SourceNotEnabledReason | None = None) -> None:
        if reason is not None and not isinstance(reason, SourceNotEnabledReason):
            raise TypeError("motivo de fuente no habilitada fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        if self.reason is None:
            return self.default_message
        return f"{self.default_message}: {self.reason.value}"


class SelectorsReason(StrEnum):
    """Conjunto cerrado de motivos por los que `selectors.yaml` no habilita el portal (llave 3)."""

    YAML_UNAVAILABLE = "falta el componente opcional del portal"
    UNREADABLE = "archivo de selectores ilegible"
    TOO_LARGE = "archivo de selectores demasiado grande"
    INVALID_YAML = "YAML inválido"
    INVALID_STRUCTURE = "estructura de selectores inválida"
    OUTSIDE_PROJECT = "archivo de selectores fuera del proyecto"
    DUPLICATE_KEY = "clave duplicada en el YAML"
    FORBIDDEN_TARGET = "un selector del formulario o resultado apunta al desafío"
    INVALID_APPROVAL_REF = "la referencia de aprobación esperada no es válida"
    SYNTHETIC = "archivo de selectores sintético"
    NOT_SYNTHETIC = "el archivo no es sintético"
    NOT_VALIDATED = "selectores sin validar"
    APPROVAL_MISMATCH = "la referencia de aprobación no coincide"
    SNAPSHOT_MISSING = "falta la referencia al snapshot documentado"
    PLACEHOLDER = "quedan marcadores de posición pendientes"
    MAINTENANCE_MARKERS_EMPTY = "faltan marcadores de mantenimiento"
    CHALLENGE_MARKERS_MISSING = "faltan marcadores de desafío o su evidencia"
    BLOCK_MARKERS_MISSING = "faltan marcadores de bloqueo o su evidencia"


class SelectorsNotValidatedError(RutCheckerError):
    """Los selectores del portal no han sido validados contra un snapshot real.

    Sin motivo usa el mensaje genérico; el motivo es de un conjunto cerrado (sin rutas ni valores
    del YAML).
    """

    default_message = "Los selectores del portal no están validados"

    def __init__(self, reason: SelectorsReason | None = None) -> None:
        if reason is not None and not isinstance(reason, SelectorsReason):
            raise TypeError("motivo de selectores fuera del conjunto cerrado")
        self.reason = reason
        super().__init__()

    def _message(self) -> str:
        if self.reason is None:
            return self.default_message
        return f"{self.default_message}: {self.reason.value}"


class FakeNotAllowedError(RutCheckerError):
    """La fuente de pruebas no está permitida en este entorno."""

    default_message = "La fuente de pruebas no está permitida"
