# Estado del proyecto

**Fase actual:** 1 — Levantamiento de requisitos
**Estado de la fase:** EN_CURSO
**Última actualización:** 2026-10-09

## Gates de fase

| Fase | Estado | Aprobado por | Fecha |
|---|---|---|---|
| 1. Requisitos | EN_CURSO | — | — |
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

## Supuestos activos

- SUPUESTO: lotes ≤ 200 identificaciones por ejecución.
- SUPUESTO: el operador puede atender pausas de verificación humana.
- SUPUESTO: salida en Excel + JSON.

## Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R-01 | El portal sigue en mantenimiento o desaparece | Alta | Alto | Puerto intercambiable + contingencia manual |
| R-02 | Captcha en cada consulta hace inviable el volumen | Media | Alto | Modo asistido; evaluar proveedor comercial / canal oficial |
| R-03 | Cambios del HTML rompen la extracción | Alta | Medio | Selectores en config, detección `ESTRUCTURA_CAMBIADA`, fixtures |
| R-04 | Uso no autorizado / incumplimiento de condiciones | Media | Alto | Fase 2 + consulta formal DIAN antes de producción |
| R-05 | Fuga de datos personales en logs/repo | Baja | Alto | Enmascarado, hooks, .gitignore, revisión de seguridad |

## Pendientes / bloqueos

- Respuestas del responsable del requerimiento (specs/requisitos.md §Preguntas).
- Verificar en navegador real el estado de la URL original.

## Bitácora

- 2026-10-09 — Andamiaje de agentes, skills, comandos, hooks y specs creado.
