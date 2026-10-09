# SPEC — Consulta automatizada del estado del RUT

> Versión 0.1 · 2026-10-09 · Estado: **BORRADOR** (requisitos y fuente de datos sin validar)
> Convención de hallazgos: **[CONFIRMADO]** fuente verificable · **[PENDIENTE]** requiere confirmación · **[DESCARTADO]** con motivo · **[SUPUESTO]** decisión provisional

## 1. Problema

Hoy una persona entra al portal de la DIAN, digita un número de identificación, resuelve la verificación
de seguridad y copia manualmente el resultado (estado del RUT, nombre/razón social, etc.).
Es lento, repetitivo, propenso a errores y no deja trazabilidad.

## 2. Flujo esperado (TO-BE de alto nivel)

1. **Ingresar la cédula/NIT** — individual o por lote (Excel/CSV).
2. **Ejecutar la consulta** — un robot abre el canal oficial e introduce la información.
3. **Consultar y extraer** — se obtienen solo los campos necesarios.
4. **Entregar el resultado** — se presentan o exportan al sistema que defina el negocio.

## 3. Situación conocida al 2026-10-09

| # | Hallazgo | Clasificación |
|---|---|---|
| H1 | El portal `https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces` fue reportado en mantenimiento por el responsable del proyecto (imagen oficial `Mantenimiento-Consulta-RUT.jpg`). Verificado en navegador real el 2026-10-09 14:20:55 COT: 302 → imagen oficial de mantenimiento, sin fecha de regreso (`docs/investigacion/01-estado-url.md`). | [CONFIRMADO] 2026-10-09 |
| H2 | Proveedores comerciales (Kontalid, ConsultorContable, Actualícese) automatizan el portal público y declaran que dependen de que la DIAN "lo permita". | [CONFIRMADO] en sus páginas comerciales |
| H3 | El portal usa una verificación tipo Cloudflare/captcha; la opción "Estado del RUT" se reportó intermitente en mayo–junio de 2026 (comentarios de un proveedor, no fuente oficial). | [PENDIENTE] confirmar en el portal |
| H4 | No se encontró una API pública oficial de la DIAN para consulta del estado del RUT por terceros. | [PENDIENTE] confirmar con DIAN (PQRSD / canales de servicio) |
| H5 | La automatización debe detenerse ante captcha; resolverlo automáticamente está prohibido por las reglas del proyecto. | [CONFIRMADO] regla del proyecto |

Consecuencia: **la fuente de datos es incierta**. La arquitectura debe aislarla detrás de un puerto
(`RutSourcePort`) para poder cambiar entre: portal oficial (RPA), servicio oficial/API si aparece,
validación documental o contingencia manual — sin reescribir el resto.

## 4. Alcance funcional (inicial, por validar)

| ID | Requisito | Prioridad MVP |
|---|---|---|
| RF-01 | Consulta individual por número de identificación | Must |
| RF-02 | Consulta por lote desde Excel/CSV | Must [SUPUESTO: lotes ≤ 200 por ejecución] |
| RF-03 | Validar formato (solo dígitos, longitud, DV si es NIT) antes de consultar | Must |
| RF-04 | Automatizar navegación, diligenciamiento y envío en el canal oficial | Must (si Fase 2 lo aprueba) |
| RF-05 | Extraer solo campos autorizados (ver §5) | Must |
| RF-06 | Exportar a Excel | Must · JSON/CSV Could (destino confirmado: solo Excel) |
| RF-07 | Registro técnico por consulta: id de ejecución, id enmascarado, estado, inicio, duración, error | Must |
| RF-08 | Manejo de excepciones con estados identificables (`specs/excepciones.md`) | Must |
| RF-09 | Reintentos controlados con backoff solo para errores transitorios | Must |
| RF-10 | Pausa y entrega al humano ante captcha/bloqueo (modo asistido) | Must |
| RF-11 | Evitar consultas duplicadas dentro del mismo lote | Should |
| RF-12 | Modo contingencia: genera registro "pendiente de validación manual" cuando el canal no está disponible | Must |
| RF-13 | Interfaz gráfica | Won't (MVP) — CLI + archivos |
| RF-14 | Revalidación periódica de la base de terceros | Won't (MVP) — RN-04 [CONFIRMADO 2026-10-09]: se revalida solo al vincular o renovar; sin periodicidad automática |

**Contexto confirmado (2026-10-09):** 100–500 consultas/mes, frecuencia mixta, modo asistido aceptado,
sin presupuesto para proveedor comercial y sin convenio con la DIAN → tras la Fase 2 (RN-08 modificada): fuente base = copia del RUT del tercero (≤ 30 días)
+ contingencia manual; el portal público "Consulta Estado RUT" vía RPA asistido solo si se cumplen las
condiciones de `docs/investigacion/INFORME-VIABILIDAD.md` §8. Detalle en `specs/requisitos.md`.

## 5. Datos

**Entrada:** número de identificación (obligatorio): cédula o NIT [CONFIRMADO]; el NIT puede traer DV.
**Salida** [CONFIRMADO con negocio; nombres finales de campo sujetos a lo que muestre el canal real en Fase 2]:
`identificacion`, `dv`, `nombre_o_razon_social`, `estado_rut`, `fecha_consulta`, `fuente`, `estado_consulta`, `observacion`.
No se extraen campos adicionales aunque sean visibles.

**Finalidad del tratamiento (Ley 1581/2012)** [CONFIRMADO]: verificar el estado tributario (RUT) de
proveedores, contratistas, clientes y empleados durante su vinculación y para su revalidación periódica.
**Retención:** 1 año; luego se eliminan los resultados.

## 6. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-01 | Seguridad: ids enmascarados en logs; sin datos reales en repo; `.env` fuera de git |
| RNF-02 | Cumplimiento: sin evasión de controles; ritmo ≥ 5 s entre consultas (configurable, nunca < 3 s) |
| RNF-03 | Mantenibilidad: selectores en `config/selectors.yaml`; cambio de portal = cambio de config + fixture |
| RNF-04 | Trazabilidad: cada fila del resultado indica fuente y fecha/hora de validación |
| RNF-05 | Calidad: cobertura ≥ 85 % en `domain` y `application`; ruff y mypy sin errores |
| RNF-06 | Portabilidad: Windows 10/11 (equipo del usuario) y Linux (CI) |
| RNF-07 | Detección de cambios: si un selector obligatorio no aparece → `ESTRUCTURA_CAMBIADA`, nunca un dato vacío silencioso |

## 7. Arquitectura propuesta (resumen; detalle en Fase 3)

```
CLI (Typer) ──► BatchQueryService ──► RutSourcePort
                   │                     ├─ DianPortalSource   (Playwright, navegador visible, modo asistido)
                   │                     ├─ ContingencySource  (marca pendiente de validación manual)
                   │                     └─ FakeSource         (pruebas)
                   ├─► Validators (domain)
                   ├─► Exporters (Excel/JSON/CSV)
                   └─► AuditLogger (JSON, ids enmascarados)
```

## 8. Criterios de aceptación

Ver `specs/criterios-aceptacion.md`.

## 9. Preguntas abiertas para el responsable del requerimiento

Ver `specs/requisitos.md` §Preguntas. Ninguna fase posterior a la 1 cierra sin respuesta o supuesto aprobado.
