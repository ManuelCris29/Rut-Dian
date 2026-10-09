# Estado del proyecto

**Fase actual:** 3 — Diseño
**Estado de la fase:** EN_CURSO
**Última actualización:** 2026-10-09

## Gates de fase

| Fase | Estado | Aprobado por | Fecha |
|---|---|---|---|
| 1. Requisitos | APROBADA | usuario | 2026-10-09 |
| 2. Viabilidad | APROBADA | usuario | 2026-10-09 |
| 3. Diseño | EN_CURSO | — | — |
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
| 2026-10-09 | Gate Fase 1 aprobado; supuestos de Fase 1 (lote ≤ 200, MVP bajo demanda, visibilidad, RN-01/02/05/07) aprobados por el usuario | /cerrar-fase |
| 2026-10-09 | Fase 2: se acepta la alternativa C (copia del RUT del tercero) + F (contingencia manual) como base; E (RPA asistido sobre portal público) condicionado; B (API/convenio) y D (proveedor comercial) descartadas. Modifica RN-08 | INFORME-VIABILIDAD.md §5–§7 |
| 2026-10-09 | E solo se habilita con: portal operativo + protocolo T-14 ejecutado por el humano + respuesta DIAN no contraria (o aceptación de riesgo firmada por jurídico tras vencer el plazo) + autorización de tratamiento de los titulares | INFORME-VIABILIDAD.md, revisión de seguridad |
| 2026-10-09 | Antigüedad máxima de la copia del RUT aceptada: ≤ 30 días | decisión del usuario |
| 2026-10-09 | Copias del RUT: repositorio documental de acceso restringido, fuera del repo; nunca procesadas por la herramienta ni por IA | revisión de seguridad |
| 2026-10-09 | Uso interno exclusivo de la empresa responsable; la herramienta no se ofrece a terceros | Términos de uso DIAN |

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
| R-07 | Portal "Consulta Estado RUT" en mantenimiento sin fecha de regreso [CONFIRMADO 2026-10-09 14:20 COT] | Alta | Alto | C + F como base; revisión semanal de la URL (01-estado-url.md) |
| R-08 | El RUT "no tiene carácter de registro público" (Oficio 1350/2019; ET 555-2, 583, 584): conservar/reutilizar resultados 1 año podría exceder "los fines de su creación" | Media | Alto | Concepto jurídico + preguntas en PQRSD |
| R-09 | Falta autorización de tratamiento de terceros (Ley 1581 art. 9) / política de tratamiento / RNBD | Media | Alto | Autorización en formatos de vinculación como precondición de C y E |
| R-10 | Copias del RUT contienen datos excedentes (incl. cédulas de representantes/contador) | Media | Alto | Minimización: solo metadatos en la herramienta; PDF en repositorio restringido con retención definida |

## Pendientes / bloqueos

- ~~Verificar en navegador real el estado de la URL original~~ → hecho 2026-10-09 (mantenimiento). Repetir semanalmente (humano).
- T-14 BLOQUEADA: análisis técnico del formulario y captcha hasta que el portal vuelva (protocolo en 05-analisis-tecnico.md, ≤ 5 consultas autorizadas, ejecuta el humano).
- Humano: revisar, firmar y radicar la PQRSD (06-borrador-pqrsd.md); decidir si se copia a la Dirección de Gestión Jurídica.
- Jurídico / responsable de datos: concepto sobre reserva del RUT, art. 10 Ley 1581 y cláusula "servicios privados o con fines de lucro".
- Negocio: incluir en formatos de vinculación la solicitud de copia del RUT (≤ 30 días) y la autorización de tratamiento.
- Re-verificación de seguridad: APROBADO (2026-10-09); 12 observaciones corregidas.

## Bitácora

- 2026-10-09 — Andamiaje de agentes, skills, comandos, hooks y specs creado.
- 2026-10-09 — Repositorio git inicializado; primer commit del andamiaje (orquestador).
- 2026-10-09 — Fase 1 ronda 1: 12 preguntas respondidas; requisitos.md, SPEC §4–§5, criterios y tareas actualizados (orquestador en rol analista-requisitos).
- 2026-10-09 — Gate de Fase 1 aprobado por el usuario; inicia Fase 2 — Viabilidad (orquestador).
- 2026-10-09 — Fase 2: T-10..T-13, T-15, T-16 hechas; T-14 bloqueada por mantenimiento (investigador-dian). Revisión de seguridad: APROBADO CON OBSERVACIONES, 4 mayores y 8 menores (revisor-seguridad). Usuario acepta C+F / E condicionado y copia RUT ≤ 30 días (orquestador).
- 2026-10-09 — Correcciones aplicadas (investigador-dian); re-verificación de seguridad APROBADO (revisor-seguridad); SPEC H1/§4 y RN-07 actualizados (orquestador). Fase 2 lista para gate.
- 2026-10-09 — Gate de Fase 2 aprobado por el usuario; inicia Fase 3 — Diseño (orquestador).
