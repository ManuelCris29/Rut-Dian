# Catálogo de estados y excepciones

Cada consulta termina en **exactamente un** `QueryStatus`. El mensaje al usuario nunca incluye el número completo.

| QueryStatus | Cuándo | Reintento | Acción de recuperación | Mensaje al usuario |
|---|---|---|---|---|
| `EXITOSA` | Resultado extraído y validado | — | — | "Consulta completada" |
| `SIN_RESULTADOS` | El canal indica que no hay registro | No | Revisar número con el solicitante | "La DIAN no devolvió registro para este número" |
| `ENTRADA_INVALIDA` | Vacío, no numérico, longitud fuera de rango, DV incorrecto | No | Corregir dato de entrada | "Número inválido: {motivo}" |
| `PORTAL_NO_DISPONIBLE` | HTTP 5xx, página de mantenimiento, DNS/conexión | Sí (máx 2, backoff 30 s/120 s) | Si persiste → contingencia | "El servicio de la DIAN no está disponible" |
| `TIEMPO_AGOTADO` | Navegación o espera de resultado > timeout | Sí (máx 2) | Revisar conectividad | "Se agotó el tiempo de espera" |
| `ESTRUCTURA_CAMBIADA` | Selector obligatorio ausente | **No** — detiene el lote | Actualizar `selectors.yaml` + fixture | "El portal cambió; se requiere mantenimiento" |
| `RESULTADO_INCOMPLETO` | Faltan campos obligatorios en el resultado | No | Revisión manual | "Resultado incompleto" |
| `SESION_VENCIDA` | El canal reinicia sesión/vista | Sí (1, con página nueva) | — | "La sesión expiró; se reintentó" |
| `REQUIERE_INTERVENCION_HUMANA` | Captcha/Turnstile/bloqueo no resuelto por el humano en el tiempo de espera | **No automático** | El operador decide continuar o detener | "Se requiere verificación humana" |
| `PENDIENTE_VALIDACION_MANUAL` | Modo contingencia | No | Validar manualmente y registrar fuente/fecha | "Pendiente de validación manual" |
| `ERROR_EXPORTACION` | Falla al escribir el archivo de salida | Sí (1, ruta alternativa) | Se guarda JSON de respaldo | "No se pudo exportar a {formato}" |
| `ERROR_ALMACENAMIENTO` | Solo si existe BD | Sí (1) | — | "No se pudo guardar el resultado" |

## Reglas

- Bloqueo detectado 2 veces seguidas → el lote **se detiene** (no seguir insistiendo contra el portal).
- `ESTRUCTURA_CAMBIADA` → se detiene y se guarda un snapshot **sanitizado** del DOM (sin datos personales) en `logs/` (fuera de git).
- Ningún error técnico se traduce en un `estado_rut` inventado.
