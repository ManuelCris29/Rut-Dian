# Estado del proyecto

**Fase actual:** 1 — Levantamiento de requisitos
**Estado de la fase:** LISTA_PARA_GATE (espera aprobación humana)
**Última actualización:** 2026-10-09

## Gates de fase

| Fase | Estado | Aprobado por | Fecha |
|---|---|---|---|
| 1. Requisitos | LISTA_PARA_GATE | — | — |
| 2. Viabilidad | PENDIENTE | — | — |
| 3. Diseño | PENDIENTE | — | — |
| 4. Desarrollo | PENDIENTE | — | — |
| 5. Pruebas | PENDIENTE | — | — |
| 6. Producción | PENDIENTE | — | — |

## Decisiones tomadas

| Fecha | Decisión | Referencia |
|---|---|---|
| 2026-10-09 | Stack propuesto Python + Playwright (pendiente de confirmar en Fase 2) | adr/0001 |
| 2026-10-09 | La fuente de datos se aísla tras un puerto intercambiable | SPEC §3 |
| 2026-10-09 | Ante captcha/Turnstile: modo asistido o parada; nunca resolución automática | CLAUDE.md §3 |
| 2026-10-09 | Modo asistido aceptado por el negocio | requisitos.md #9 |
| 2026-10-09 | Fuente objetivo: portal público "Consulta Estado RUT" (sin convenio DIAN, sin presupuesto para proveedor) | requisitos.md #11–12, RN-08 |
| 2026-10-09 | Salida MVP: solo Excel; JSON/CSV pasan a Could | SPEC RF-06 |
| 2026-10-09 | Finalidad: vinculación/verificación de proveedores, contratistas, clientes y empleados; retención 1 año | SPEC §5, RN-06 |
| 2026-10-09 | Información exógena fuera de alcance | requisitos.md |

## Supuestos activos

- SUPUESTO: lotes ≤ 200 identificaciones por ejecución (picos de volumen sin confirmar).
- SUPUESTO: MVP solo bajo demanda; la periodicidad de revalidación (RN-04) se define en Fase 3.
- SUPUESTO: pueden ver los resultados el área solicitante y el operador.
- SUPUESTO: línea base > 3 min/consulta → > 5–25 h operador/mes; se confirma cronometrando 20 consultas.

## Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R-01 | El portal sigue en mantenimiento o desaparece | Alta | Alto | Puerto intercambiable + contingencia manual |
| R-02 | Captcha en cada consulta hace inviable el volumen | Media | Medio | Modo asistido aceptado; con 100–500/mes sigue siendo viable aunque haya captcha frecuente |
| R-06 | Sin proveedor ni convenio: si el portal público no es utilizable no hay alternativa automatizada | Media | Alto | Contingencia manual + validación contra copia del RUT (RN-07) + PQRSD a la DIAN (T-16) |
| R-03 | Cambios del HTML rompen la extracción | Alta | Medio | Selectores en config, detección `ESTRUCTURA_CAMBIADA`, fixtures |
| R-04 | Uso no autorizado / incumplimiento de condiciones | Media | Alto | Fase 2 + consulta formal DIAN antes de producción |
| R-05 | Fuga de datos personales en logs/repo | Baja | Alto | Enmascarado, hooks, .gitignore, revisión de seguridad |

## Pendientes / bloqueos

- Verificar en navegador real el estado de la URL original.

## Bitácora

- 2026-10-09 — Andamiaje de agentes, skills, comandos, hooks y specs creado.
- 2026-10-09 — Repositorio git inicializado; primer commit del andamiaje (orquestador).
- 2026-10-09 — Fase 1 ronda 1: 12 preguntas respondidas; requisitos.md, SPEC §4–§5, criterios y tareas actualizados (orquestador en rol analista-requisitos).
