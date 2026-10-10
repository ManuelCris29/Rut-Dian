# Estado del proyecto

**Fase actual:** 4 — Desarrollo
**Estado de la fase:** EN_CURSO
**Última actualización:** 2026-10-09

## Gates de fase

| Fase | Estado | Aprobado por | Fecha |
|---|---|---|---|
| 1. Requisitos | APROBADA | usuario | 2026-10-09 |
| 2. Viabilidad | APROBADA | usuario | 2026-10-09 |
| 3. Diseño | APROBADA | usuario | 2026-10-09 |
| 4. Desarrollo | EN_CURSO | — | — |
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
| 2026-10-09 | D-1: nuevo estado `VALIDADA_COPIA_RUT` para filas validadas contra copia ≤ 30 días | ADR-0002, excepciones.md |
| 2026-10-09 | D-2 (RN-04): revalidación solo al vincular/renovar; sin periodicidad en el MVP | requisitos.md RN-04 |
| 2026-10-09 | D-3: el operador no transcribe nombre/estado desde la copia del RUT (minimización) | ADR-0002 |
| 2026-10-09 | D-4: fixtures HTML sintéticos permitidos solo para probar el mecanismo de detección/pausa, con condiciones de revisor-seguridad | ADR-0003, tareas T-38/T-49 |
| 2026-10-09 | D-5: snapshot de diagnóstico ante ESTRUCTURA_CAMBIADA desactivado por defecto; si se activa, solo esqueleto estructural sin textos | ARQUITECTURA, excepciones.md |
| 2026-10-09 | P-4: entrada = una columna con el número; DV opcional | ARQUITECTURA |
| 2026-10-09 | Gherkin G9–G12 incorporados a criterios de aceptación | criterios-aceptacion.md |

## Supuestos activos

- SUPUESTO: lotes ≤ 200 identificaciones por ejecución (picos de volumen sin confirmar).
- SUPUESTO: MVP solo bajo demanda; la periodicidad de revalidación (RN-04) se define en Fase 3.
- SUPUESTO: pueden ver los resultados el área solicitante y el operador.
- SUPUESTO: línea base > 3 min/consulta → > 5–25 h operador/mes; se confirma cronometrando 20 consultas.
- SUPUESTO: longitudes válidas 3–10 dígitos (cédula 3–10, NIT 9–10 sin DV); ceros iniciales se conservan (afecta dedupe: "01234567" ≠ 1234567). Confirmar con negocio.
- SUPUESTO (P-4): sin columna de tipo ni guion, un número de 10 dígitos se toma como identificación sin DV; un NIT con DV pegado sin guion no se distingue de una cédula de 10 dígitos.

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
| R-11 | Fuga de ids/nombres por mensajes de excepción de terceros (call log de Playwright, tracebacks con locales de Typer) | Media | Alto | Solo error_code y clase en logs; show_locals=False; MaskingFilter sobre exc_info; pruebas T-40/T-43 |
| R-12 | Archivos con datos personales fuera de `output/` (OneDrive, repo, rutas arbitrarias) | Media | Alto | --salida restringido a RUT_OUTPUT_DIR; guía de carpeta y ACL (T-60); purgar cubre data/output/logs |
| R-13 | Selectores sintéticos o aprobación falsa habilitan el portal (E) sin cumplir (a)–(d) | Baja | Alto | Triple llave endurecida (formato APPROVAL_REF, synthetic rechazado, host *.dian.gov.co); el registro de aprobación en ESTADO.md cita evidencia de (a)–(d) con fecha y firmante |
| R-14 | Inyección de fórmulas / XML malicioso en Excel | Baja | Medio | Neutralizar `= + - @ \t \r`; defusedxml |
| R-15 | Conservar 1 año resultados del portal (V-10) excede "fines de su creación" | Media | Alto | Retención configurable ≤ 365; purgar --fuente PORTAL_DIAN_C1; concepto jurídico |

## Pendientes / bloqueos

- ~~Verificar en navegador real el estado de la URL original~~ → hecho 2026-10-09 (mantenimiento). Repetir semanalmente (humano).
- T-14 BLOQUEADA: análisis técnico del formulario y captcha hasta que el portal vuelva (protocolo en 05-analisis-tecnico.md, ≤ 5 consultas autorizadas, ejecuta el humano).
- Humano: revisar, firmar y radicar la PQRSD (06-borrador-pqrsd.md); decidir si se copia a la Dirección de Gestión Jurídica.
- Jurídico / responsable de datos: concepto sobre reserva del RUT, art. 10 Ley 1581 y cláusula "servicios privados o con fines de lucro".
- Negocio: incluir en formatos de vinculación la solicitud de copia del RUT (≤ 30 días) y la autorización de tratamiento.
- Re-verificación de seguridad: APROBADO (2026-10-09); 12 observaciones corregidas.
- T-31 BLOQUEADA (humano): crear remoto GitHub, push, rama `verif/ci-rojo` (prueba fallida + `sed` de requests==2.19.0 en el requirements exportado) → rojo en quality/audit, revertir → verde; reemplazar `<<PROPIETARIO>>` en `.github/CODEOWNERS` y activar "Require review from Code Owners".
- Humano (opcional): ampliar `.claude/hooks/bloquear_evasion.py` con `ignore_default_args`, `add_init_script`, `extra_http_headers`, `ignore_https_errors`, `clear_cookies` (propuesta revisor-seguridad Fase 3).
- Para T-38: `context.route` que aborte todo salvo localhost/file://; valorar cubrir `getaddrinfo` en el guard; pruebas `portal_real` con variable de opt-in explícita (revisor-seguridad).
- Para T-37/T-40 (revisor-seguridad T-33): pruebas de `build_service` con `dian_portal` sin `RUT_PORTAL_ENABLED`, `fake` sin `RUT_ALLOW_FAKE`, y snapshot con fuente distinta del portal (valorar exigir `portal_enabled`). La CLI muestra si cargó `.env` y desde qué ruta (sin valores); T-60 documenta ejecutar desde la raíz.
- Para T-43: `MaskingFilter` también sobre `record.exc_text`/`stack_info` y excepciones encadenadas (`__cause__` de Playwright); adaptadores con `from None` o solo `type(exc).__name__`; prueba con excepción encadenada que lleve un id.
- Para T-46/T-40b: crear `output/` y `logs/` con permisos restringidos; aviso si la ruta está en OneDrive/Dropbox/Google Drive.
- Para T-36 (servicio): pausa efectiva antes de reintento = max(min_delay, backoff).

## Bitácora

- 2026-10-09 — Andamiaje de agentes, skills, comandos, hooks y specs creado.
- 2026-10-09 — Repositorio git inicializado; primer commit del andamiaje (orquestador).
- 2026-10-09 — Fase 1 ronda 1: 12 preguntas respondidas; requisitos.md, SPEC §4–§5, criterios y tareas actualizados (orquestador en rol analista-requisitos).
- 2026-10-09 — Gate de Fase 1 aprobado por el usuario; inicia Fase 2 — Viabilidad (orquestador).
- 2026-10-09 — Fase 2: T-10..T-13, T-15, T-16 hechas; T-14 bloqueada por mantenimiento (investigador-dian). Revisión de seguridad: APROBADO CON OBSERVACIONES, 4 mayores y 8 menores (revisor-seguridad). Usuario acepta C+F / E condicionado y copia RUT ≤ 30 días (orquestador).
- 2026-10-09 — Correcciones aplicadas (investigador-dian); re-verificación de seguridad APROBADO (revisor-seguridad); SPEC H1/§4 y RN-07 actualizados (orquestador). Fase 2 lista para gate.
- 2026-10-09 — Gate de Fase 2 aprobado por el usuario; inicia Fase 3 — Diseño (orquestador).
- 2026-10-09 — Fase 3: T-20..T-24 entregadas (arquitecto). Revisión de seguridad del diseño: APROBADO CON OBSERVACIONES, 6 mayores y 9 menores (revisor-seguridad). Usuario decide D-1..D-5, P-4 y Gherkin G9–G12 (orquestador). Arquitecto aplicando correcciones.
- 2026-10-09 — Fase 3: correcciones aplicadas (arquitecto); re-verificación de seguridad APROBADO; 5 pendientes menores corregidos (orquestador). Fase 3 lista para gate.
- 2026-10-09 — Gate de Fase 3 aprobado por el usuario (ADR-0001..0003 ratificados); inicia Fase 4 — Desarrollo (orquestador).
- 2026-10-09 — T-30 HECHA: esqueleto uv/ruff/mypy/pytest, prueba de arquitectura con ast, guard de red (incl. asyncio/Proactor/UDP); 35 pruebas en verde; revisor-codigo APROBADO CON OBSERVACIONES tras 2 iteraciones (desarrollador-python).
- 2026-10-09 — T-31: CI (quality ubuntu+windows, coverage, audit con pip-audit fijado, integration condicionado), CODEOWNERS en borrador, .gitignore ampliado; revisores código y seguridad APROBADO CON OBSERVACIONES, aplicadas. BLOQUEADA a la espera de verificación en GitHub (ingeniero-devops).
- 2026-10-09 — T-32 HECHA: QueryStatus (incl. VALIDADA_COPIA_RUT), SourceKind, excepciones sin mensaje libre, enmascarado (≤ 6 caracteres → todo *; ≥ 7 → últimos 4; regex sin \s); 86 pruebas; revisor-codigo APROBADO CON OBSERVACIONES tras 2 iteraciones (desarrollador-python).
- 2026-10-09 — T-33 HECHA: Settings (pydantic-settings, valores seguros, triple llave: APPROVAL_REF con fecha real, URL https solo *.dian.gov.co:443 sin userinfo ni \, backoff ≥ 3 y ≥ max_retries), .env.example, aislamiento del .env real en pruebas; 157 pruebas; revisor-codigo APROBADO CON OBSERVACIONES; revisor-seguridad BLOQUEANTE (evasión de URL con \) → corregido → APROBADO CON OBSERVACIONES (desarrollador-python).
- 2026-10-09 — T-42 HECHA: modelos de dominio frozen (InputRow, IdentificationInput, CopyEvidence, RutResult con invariantes estado↔fuente, QueryOutcome), regla de copia ≤ 30 días con CopyVerdict VALID/EXPIRED/FUTURE_DATE, errores de dominio en validadores before, repr enmascarado; 246 pruebas; revisor-codigo APROBADO CON OBSERVACIONES tras 2 iteraciones. Deuda: model_dump expone datos reales → no volcar modelos a logs (T-43) (desarrollador-python).
- 2026-10-09 — T-41 HECHA: validadores (normalización con agrupación de miles válida y decimal nulo .0/,00; sin espacios mezclados con . o ,; guiones Unicode; DV con stdnum solo si llega; todo-ceros rechazado; firma sin row_index); 396 pruebas; revisor-codigo APROBADO CON OBSERVACIONES tras 2 iteraciones (2 hallazgos de identificación equivocada silenciosa corregidos). Deuda: regex _DIGITS duplicadas en models/validators (desarrollador-python).
