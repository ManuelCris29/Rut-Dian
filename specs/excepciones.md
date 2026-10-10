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
| `PENDIENTE_VALIDACION_MANUAL` | Modo contingencia; sin copia del RUT; copia > 30 días ("copia vencida"); fecha de copia futura (en ambos casos `fuente` = `CONTINGENCIA_MANUAL`); portal caído tras reintentos; filas restantes de un lote detenido | No | Validar manualmente y registrar fuente/fecha | "Pendiente de validación manual" |
| `VALIDADA_COPIA_RUT` | El área de vinculación registró una copia del RUT del tercero con antigüedad ≤ 30 días (fecha y responsable). La herramienta no lee el PDF; `estado_rut` y `nombre_o_razon_social` quedan vacíos (D-1, D-3, 2026-10-09) | No | Revalidar en C-1 cuando vuelva, si el negocio lo requiere | "Validado contra copia del RUT de fecha AAAA-MM-DD" |
| `ERROR_EXPORTACION` | Falla al escribir el archivo de salida | Sí (1, ruta alternativa) | Se guarda JSON de respaldo | "No se pudo exportar a {formato}" |
| `ERROR_ALMACENAMIENTO` | Solo si existe BD | Sí (1) | — | "No se pudo guardar el resultado" |

## Reglas

- Bloqueo detectado 2 veces seguidas → el lote **se detiene** (no seguir insistiendo contra el portal).
- `ESTRUCTURA_CAMBIADA` → se detiene el lote. El snapshot de diagnóstico está **desactivado por defecto** (D-5, 2026-10-09); solo con `RUT_DIAGNOSTIC_SNAPSHOT=true` y `RUT_PORTAL_APPROVAL_REF` vigente se guarda un esqueleto estructural sin textos ni valores en `logs/snapshot_<run_id>_<row_index>.html` (nunca screenshot, trace, video ni HAR; retención 30 días). Ver `docs/ARQUITECTURA.md` §10.
- 3 `TIEMPO_AGOTADO` seguidos (tras sus reintentos; el contador se reinicia con `EXITOSA` o `SIN_RESULTADOS`) → se abre el circuito: el resto del lote va a la fuente de respaldo (constante, no configurable).
- `ERROR_EXPORTACION` es de nivel ejecución (código de salida 3): las filas conservan su estado.
- `ERROR_ALMACENAMIENTO` no se implementa: no hay base de datos (ARQUITECTURA §12).
- Ningún error técnico se traduce en un `estado_rut` inventado.
