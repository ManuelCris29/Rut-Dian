# Informe de viabilidad — Consulta del estado del RUT de terceros (Fase 2, T-15)

> Agente: investigador-dian · Versión 1.0 · 2026-10-09 · America/Bogota
> Evidencia detallada: `01-estado-url.md` … `06-borrador-pqrsd.md`. Convención: [CONFIRMADO] · [PENDIENTE] · [DESCARTADO] · [SUPUESTO].
> No es asesoría legal.

## 1. Resumen ejecutivo

- **Hoy (2026-10-09 14:20:55 COT) el servicio oficial "Consulte su estado RUT" está fuera de operación**: la URL responde 302 hacia una imagen oficial de la DIAN que anuncia "ajustes tecnológicos", sin fecha de regreso. [CONFIRMADO]
- **No se encontró un canal oficial (API, servicio web o convenio) disponible para que una empresa privada consulte de forma automatizada el estado del RUT de terceros.**
  - [CONFIRMADO] Los servicios web del RUT son para entidades públicas con convenio, y la DIAN sostiene que el RUT "no tiene el carácter de registro público" y que no comparte su información con privados (Oficio 1350/2019).
  - [CONFIRMADO] El servicio de datos del adquiriente (C-6, Res. 202/2025) prohíbe el "uso masivo" y se limita a facturar.
  - [PENDIENTE] Falta la confirmación formal de que no existe una API pública para particulares (PQRSD, 06).
- Los proveedores comerciales automatizan **el mismo portal público** y fallan cuando este falla. Además, las condiciones del portal prohíben usar sus servicios para "servicios privados o con fines de lucro". [CONFIRMADO]
- Quedan como [PENDIENTE: concepto jurídico]:
  - si la reserva tributaria (ET art. 583) y las restricciones del Oficio 1350/2019 alcanzan los datos que muestra C-1;
  - si es lícito conservarlos 1 año.
- **Recomendación — ACEPTADA por el usuario el 2026-10-09:**
  - operar ya con **C + F**: validación documental con la copia del RUT entregada por el tercero, con antigüedad **≤ 30 días** (decisión del usuario), más contingencia manual trazable;
  - construir **E (RPA asistido)** como adaptador **condicionado**, habilitable solo si se cumplen las condiciones (a)–(d) de §8;
  - **B y D quedan descartadas**.
  - La arquitectura con `RutSourcePort` sigue siendo correcta.
- **RN-08 se modifica** (decisión del usuario del 2026-10-09). La fuente deja de ser "solo el portal público" y pasa a ser: **C + F como base; E condicionado; A manual para revalidar**. El orquestador debe reflejarlo en `specs/requisitos.md` y `docs/ESTADO.md`.

## 2. Estado verificado de la URL y fecha

| Campo | Valor |
|---|---|
| URL | https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces |
| Fecha/hora | 2026-10-09 14:20:55 America/Bogota |
| Método | Navegador real (Playwright, Chromium visible, sin stealth), observación pasiva; HTTP directo bloqueado por el hook del proyecto |
| Respuesta | 302 → `https://www.dian.gov.co/impuestos/RUT/PublishingImages/Mantenimiento-Consulta-RUT.jpg` (200) |
| Mensaje | "…la funcionalidad de Consulta estado RUT… permanecerá temporalmente fuera de operación mientras culminan las actividades programadas." |
| Desafío de seguridad | No observable (no hay formulario) → [PENDIENTE] |
| Clasificación | H1 → **[CONFIRMADO]** |

Pendiente para el humano: confirmar en su navegador y registrar comprobaciones semanales (tabla en 01).

## 3. Alternativas oficiales

| Canal | Para qué sirve | ¿Sirve para consultar terceros? | Estado |
|---|---|---|---|
| C-1 Consulte su estado RUT | Consulta pública del estado por NIT o cédula | **Sí** (único canal oficial para terceros) | En mantenimiento [CONFIRMADO] |
| C-2 Solicitar copia del RUT | El titular obtiene su propio RUT (cuenta + firma electrónica) | No; el tercero lo obtiene y lo entrega (alt. C) | Publicado [CONFIRMADO] |
| C-3 Consultas "a nombre de un tercero" | Representante, revisor o contador de **su** entidad | No (terceros arbitrarios) | [DESCARTADO] |
| C-4 Inscripción/actualización | Trámite del titular | No | [DESCARTADO] |
| C-5 RUT sin correo electrónico | Verifica si hay correo registrado; orientado al titular | No (otra finalidad) | [DESCARTADO] |
| C-6 Servicio de datos del adquiriente (Res. 202/2025) | Nombre y correo del comprador al facturar | No: "únicamente" para facturar, "En ningún caso… uso masivo"; no devuelve el estado | [DESCARTADO] |
| C-7 Intercambio de información / web services RUT | Entidades públicas o que cumplen funciones públicas, con convenio | No para privados (Oficio 1350/2019) | [DESCARTADO] |
| C-8 API pública de estado del RUT | — | No encontrada | [PENDIENTE] confirmar vía PQRSD |
| C-9 PQRSD / C-10 Contact Center y chat | Consulta formal / soporte | Medio para pedir el canal autorizado | [CONFIRMADO] / [PENDIENTE] número vigente |

## 4. Evidencia de empresas

- **Kontalid** declara que "se conecta a la DIAN como una automatización de la página Consulta Estado RUT" y que "cuando esta consulta no esta funcionando, la consulta de Kontalid tampoco funcionará" (páginas consultadas el 2026-10-09; actualizaciones de 2024 y marzo de 2025).
- **ConsultorContable** vende una extensión de navegador ($110.000/año) cuya opción "Estado del RUT" "no es estable" por "Cloudflare o Captcha"; comentarios fechados reportan intermitencia o inhabilitación entre 2025-05 y 2026-06.
- **Actualícese** ofrece un validador de hasta 1.000 NIT por operación con "nombre, correo electrónico y estado de proveedor ficticio"; **no declara el estado del RUT** y no revela su fuente [PENDIENTE].
- **ERP y proveedores tecnológicos** (Alegra, Odoo, The Factory HKA, entre otros) integran el servicio del adquiriente **para facturar**, no para validar el estado del RUT.
- Ningún proveedor demuestra convenio o autorización de la DIAN. [PENDIENTE]
Detalle y citas: `04-practicas-mercado.md`.

## 5. Comparación

| Alternativa | Fuente de evidencia | Disponibilidad verificada | Requisitos de acceso | Posibilidad de automatización | Costos conocidos | Limitaciones | Recomendación |
|---|---|---|---|---|---|---|---|
| **A. Servicio oficial de consulta (uso manual de C-1)** | 01; página RUT de la DIAN; ficha SUIT 76849 (2026-10-09) | **No**: en mantenimiento (2026-10-09 14:20:55), sin fecha de regreso | Ninguno (público); desafío de seguridad reportado [PENDIENTE] | No (manual); base de E | Gratuito (SUIT) · costo operador: más de 3 min por consulta | Indisponible hoy; intermitente desde 2025-05 (fuente no oficial); condiciones de uso | **Mantener** como verificación manual cuando vuelva · [CONFIRMADO] existencia / [PENDIENTE] retorno |
| **B. API / servicio web / interoperabilidad** | Catálogo de intercambio (PDF DIAN 2021); Oficio 1350/2019; Res. 202/2025 | Existe solo para entidades públicas con convenio (C-7) y para facturar (C-6) | Convenio con la DIAN y funciones públicas (C-7); ser facturador y finalidad de facturación (C-6) | Sí técnicamente, pero **no accesible legalmente** para este fin | Sin convenio (RN-08); C-6 gratuito pero con finalidad restringida | La DIAN no comparte el RUT con privados; C-6 prohíbe el "uso masivo" | **[DESCARTADO]** para este negocio; reabrir solo si la PQRSD informa un canal nuevo |
| **C. Validación documental (copia del RUT entregada por el tercero)** | Página RUT DIAN (copia con cuenta y firma electrónica); Oficio 1350/2019 (el titular comparte su RUT "bajo su responsabilidad") | **Sí** (no depende del portal) | El tercero entrega su copia, con antigüedad **≤ 30 días** (decisión del usuario, 2026-10-09); hoy ocurre "a veces" (requisitos #7); autorización probada del titular (condición d) | Parcial: solo registro y trazabilidad. **La herramienta no procesa el PDF** (ver la minimización de §8) | Gratuito; esfuerzo del área de vinculación | No prueba el estado **actual** (foto a la fecha del documento); autenticidad no verificable en línea [PENDIENTE] (PQRSD, pregunta 6); la DIAN no publica una vigencia | **RECOMENDADA (base) — ACEPTADA** · [CONFIRMADO] |
| **D. Proveedor comercial** | Kontalid, ConsultorContable, Actualícese (2026-10-09) | Depende del mismo C-1 → **no disponible** hoy | Licencia o suscripción | Sí (en sus términos) | $99.000 + IVA a $110.000/año; Kontalid en planes PREMIUM/ELITE | Sin presupuesto (RN-08); sin convenio demostrado; condiciones del portal ("servicios privados o con fines de lucro"); exención de responsabilidad; método opaco | **[DESCARTADO]** |
| **E. RPA asistido sobre el portal público** | 01, 03, 05 | **No** hoy (mantenimiento); desafío sin verificar | Navegador visible; operador presente; ≤ 1 consulta a la vez, ≥ 5 s de pausa | **Parcial**: navegación, diligenciamiento, extracción y exportación; el desafío lo resuelve el humano | Desarrollo interno; sin licencias | Sin autorización expresa de la DIAN; selectores desconocidos; puede volver a caer o endurecerse; se detiene ante bloqueos; uso interno exclusivo | **CONDICIONADA — ACEPTADA**: construir tras el puerto; habilitar solo si se cumplen las condiciones (a)–(d) de §8 · [PENDIENTE] |
| **F. Contingencia manual o semiautomática** | Requisito RF-12 | **Sí** | Operador | Parcial: la herramienta genera el lote `PENDIENTE_VALIDACION_MANUAL` en Excel con fuente, fecha y responsable | Tiempo del operador | No produce el estado; solo trazabilidad | **RECOMENDADA (siempre activa)** · [CONFIRMADO] |

## 6. Requisitos de acceso, permisos, costos y restricciones

| Tema | Detalle | Clasificación |
|---|---|---|
| Acceso a C-1 | Público, sin cuenta; gratuito (SUIT) | [CONFIRMADO] (SUIT vía buscador) |
| Copia del RUT | Solo el titular: cuenta MUISCA + firma electrónica | [CONFIRMADO] |
| Convenios y servicios web | Solo entidades públicas o con funciones públicas | [CONFIRMADO] Oficio 1350/2019 |
| Condiciones del portal | Acuerdo legal por el uso; prohibidas las actividades "no autorizadas" y el uso de servicios para "servicios privados o con fines de lucro"; sin cláusula sobre robots. **Restricción del proyecto: uso interno exclusivo de la empresa responsable**; no se ofrece a terceros, a empresas del grupo ni a clientes | [CONFIRMADO] |
| Protección de datos | Consultar y conservar es tratamiento (Ley 1581 art. 3); la finalidad se informa al titular (art. 4.b). **Criterio conservador:** autorización previa, expresa e informada del titular, con prueba (art. 9), como condición obligatoria (d). Política de tratamiento de la empresa conforme al Decreto 1377/2013 (compilado en el 1074/2015), con finalidad, retención de 1 año y canal de consultas y reclamos. Revisar la inscripción en el RNBD (SIC) | [CONFIRMADO] norma · [PENDIENTE] si el estado del RUT es dato público; existencia de la política y del RNBD |
| Reserva y uso restringido del RUT | ET art. 583 (reserva), arts. 555-2 y 584; D.L. 19/2012 art. 63; Ley 1437/2011 art. 27; Oficio 1350/2019 (el RUT no es registro público; uso restringido "a los fines de su creación"). Que los datos de C-1 (estado, nombre o razón social) estén o no cubiertos por la reserva, y que sea lícito conservarlos 1 año | [CONFIRMADO] art. 583 y Oficio 1350 · **[PENDIENTE: concepto jurídico]** alcance sobre C-1 y conservación; textos de 555-2 y 584 sin verificar |
| Ritmo | 1 consulta a la vez, ≥ 5 s (configurable, nunca < 3 s); 2 bloqueos seguidos = detener el lote | [CONFIRMADO] regla del proyecto |
| Costos | A, C, E y F sin costo de licencia; D descartada por presupuesto | [CONFIRMADO] |

## 7. Riesgos técnicos, legales y operativos

| ID | Riesgo | Tipo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|---|
| V-01 | C-1 sigue en mantenimiento indefinidamente o se retira | Operativo | Alta | Alto | C + F como modo base; PQRSD (pregunta 1); comprobación semanal |
| V-02 | Al volver, C-1 trae un desafío interactivo en cada consulta | Técnico | Media | Medio | Modo asistido (aceptado); medir con el protocolo de 05; si no es viable, E queda como asistente de diligenciamiento o se descarta |
| V-03 | La DIAN responde que la automatización no está permitida | Legal | Media | Alto | E queda desactivado por configuración; se sigue con A manual + C + F |
| V-04 | Interpretación de "servicios privados o con fines de lucro" aplicada al uso interno | Legal | Baja-media | Alto | Uso interno exclusivo (nunca ofrecido a terceros, a empresas del grupo ni a clientes); PQRSD (pregunta 5); concepto jurídico interno |
| V-05 | Tratamiento de datos de empleados/terceros sin autorización o aviso adecuado | Legal | Media | Alto | Condición (d): autorización previa con prueba; política de tratamiento; RNBD; minimización; retención de 1 año |
| V-06 | Copia del RUT desactualizada o alterada | Operativo | Media | Medio | Antigüedad máxima **≤ 30 días** (decisión del usuario, 2026-10-09); marcar `observacion`; revalidar en C-1 cuando vuelva |
| V-10 | Conservar y reutilizar durante 1 año el resultado de C-1 se considera un uso del RUT por fuera de "los fines de su creación" (Oficio 1350/2019) o alcanzado por la reserva | Legal | Media | Alto | [PENDIENTE: concepto jurídico]; PQRSD (preguntas 8 y 9); si es contrario, conservar solo la fuente, la fecha y el resultado mínimo, o reducir la retención |
| V-11 | Filtración de la copia del RUT (PDF con datos completos del tercero) | Seguridad | Media | Alto | Minimización de §8: el PDF va a un repositorio documental restringido y nunca lo procesan la herramienta ni agentes de IA |
| V-12 | Habilitar E por "silencio" de la DIAN | Legal | Media | Alto | Prohibido: el silencio no es autorización. Se exige la condición (c) |
| V-07 | Cambios del HTML de C-1 al regresar (los "ajustes tecnológicos" pueden cambiar el formulario) | Técnico | Alta | Medio | No escribir selectores hasta tener el snapshot; `ESTRUCTURA_CAMBIADA`; fixtures |
| V-08 | Tentación de usar endpoints JSF internos o macros de terceros | Legal/técnico | Media | Alto | Prohibido (CLAUDE.md §3, hook); se registra solo como riesgo |
| V-09 | Uso de C-6 (adquiriente) fuera de la facturación | Legal | Baja | Alto | Descartado expresamente; documentarlo en el ADR |

## 8. Recomendación

**Estrategia: "C + F ahora, E condicionado", detrás de `RutSourcePort`. ACEPTADA por el usuario el 2026-10-09** (B y D descartadas; antigüedad máxima de la copia del RUT ≤ 30 días). **RN-08 se modifica:** C + F como base, E condicionado, A manual para revalidar.

1. **Modo base inmediato (C + F):**
   - El proceso de vinculación pide al tercero su **copia del RUT** (C-2, generada por el titular), con antigüedad **≤ 30 días** a la fecha de recepción.
   - La herramienta registra por cada identificación: `fuente = COPIA_RUT_TERCERO` o `PENDIENTE_VALIDACION_MANUAL`, la fecha del documento, el responsable y una observación (RF-12, RN-07).
   - Conservar resultados de C exige la condición (d).
   - El MVP de Fase 4 prioriza: validadores, lote Excel, `ContingencySource` y exportador Excel con trazabilidad.
2. **Adaptador E (`DianPortalSource`, RPA asistido)**: se diseña en Fase 3 y se implementa en Fase 4 **sin selectores reales** hasta tener el snapshot. Se **habilita en producción** solo si se cumplen **todas** estas condiciones:
   - (a) C-1 restablecido y verificado por el humano;
   - (b) el protocolo de 05 ejecutado: desafío documentado y tiempo por consulta medido;
   - (c) la PQRSD radicada y además una de estas dos:
     - (i) **respuesta de la DIAN no contraria**; o
     - (ii) **vencido el plazo legal sin respuesta**, una **aceptación de riesgo firmada** por el área jurídica o de protección de datos y **registrada con fecha en `docs/ESTADO.md`**.
     **El silencio de la DIAN no es autorización**: sin (i) o (ii), E permanece desactivado;
   - (d) **autorización previa, expresa e informada de los titulares** (Ley 1581 art. 9), con prueba conservada, y política de tratamiento de la empresa vigente (Decreto 1377/2013, compilado en el 1074/2015) con finalidad, retención de 1 año y canal de consultas y reclamos; inscripción en el RNBD (SIC) revisada.
3. **A (consulta manual en C-1)**: el operador la usa para revalidar lo marcado como pendiente cuando el servicio vuelva.
4. **B y D: descartadas.** B se reabre solo si la DIAN informa un canal para particulares.
5. **Uso interno exclusivo:** la herramienta y sus resultados son solo para la empresa responsable del tratamiento. No se ofrecen ni se prestan a terceros, a empresas del grupo ni a clientes.

### Minimización para la alternativa C (copia del RUT)

- El **PDF de la copia del RUT** se guarda **solo en el repositorio documental de acceso restringido** de la empresa: **fuera de `data/`, `output/` y git**.
- **Nunca** lo procesan la herramienta ni agentes de IA. No hay lectura ni extracción automática del PDF.
- La herramienta **solo registra**:
  - la fuente (`COPIA_RUT_TERCERO`);
  - la fecha del documento (que debe ser **≤ 30 días**; si es mayor → `PENDIENTE_VALIDACION_MANUAL` con observación);
  - el responsable que validó;
  - una observación.
- **Retención y eliminación del PDF:** alineadas a 1 año (RN-06) o a la política documental de la empresa, si es más restrictiva. [PENDIENTE] confirmar con el responsable de datos.

Justificación: es la única combinación que funciona **hoy**, no depende de un servicio caído, no evade controles, no requiere presupuesto ni convenio y conserva el valor del proyecto (trazabilidad, lotes, Excel) mientras se aclara el canal.

**Si no hay vía automatizada oficial** (no se encontró ninguna a la fecha; la confirmación formal está pendiente de la PQRSD), la automatización posible se limita a: validar formato y DV, deduplicar, generar el lote de trabajo, registrar la evidencia documental y, cuando C-1 funcione, diligenciar en un navegador visible con el humano resolviendo cualquier desafío.

## 9. Contingencia

| Situación | Acción | Estado resultante |
|---|---|---|
| C-1 en mantenimiento (302 → imagen) | No consultar; marcar todo el lote | `PORTAL_NO_DISPONIBLE` → `PENDIENTE_VALIDACION_MANUAL` |
| Hay copia del RUT del tercero con antigüedad ≤ 30 días | El operador valida nombre/razón social y DV contra la copia; registra la fecha del documento (el PDF queda en el repositorio documental restringido) | `PENDIENTE_VALIDACION_MANUAL` con observación "validado contra copia del RUT de fecha AAAA-MM-DD" [SUPUESTO: estado nuevo por definir en Fase 3] |
| Copia del RUT con antigüedad > 30 días | Solicitar una copia nueva | `PENDIENTE_VALIDACION_MANUAL` con observación "copia vencida" |
| No hay copia | Solicitar al tercero; dejar pendiente | `PENDIENTE_VALIDACION_MANUAL` |
| Desafío no resuelto en `HUMAN_CHALLENGE_TIMEOUT_S` | Detener la fila | `REQUIERE_INTERVENCION_HUMANA` |
| 2 bloqueos seguidos | Detener el lote | Lote detenido, con reporte |
| Respuesta de la DIAN contraria a la automatización | Desactivar E por configuración (`RUT_SOURCE`) **y eliminar o depurar los resultados obtenidos con C-1 automatizado, previa valoración jurídica** (cláusula T-4 de las condiciones: "destruir inmediatamente cualquier material o información del sitio") | Solo A + C + F |
| Vence el plazo legal de la PQRSD sin respuesta | E sigue desactivado salvo aceptación de riesgo firmada y registrada en `docs/ESTADO.md` (condición c.ii) | Sin cambio |

## 10. Plan de implementación y pruebas

| Paso | Fase | Responsable | Entregable | Prueba |
|---|---|---|---|---|
| 1 | Ahora | Humano | Radicar la PQRSD (06); comprobación semanal de C-1 (tabla en 01) | Número de radicado registrado |
| 2 | Ahora | Humano + área de vinculación + responsable de datos | Formatos de vinculación con: solicitud de copia del RUT ≤ 30 días; **autorización previa, expresa e informada** (Ley 1581 art. 9) con prueba conservable; aviso de privacidad. Revisión de la política de tratamiento (Decreto 1377/2013, compilado en el 1074/2015: finalidad, retención de 1 año, canal de consultas y reclamos) y de la inscripción en el RNBD (SIC). Repositorio documental restringido para los PDF | Formato y política actualizados; prueba de autorización archivada |
| 2b | Ahora | Área jurídica / protección de datos | Concepto sobre: reserva (ET 583, 555-2, 584; D.L. 19/2012 art. 63) y datos de C-1; conservación durante 1 año (Oficio 1350/2019); uso interno frente a la cláusula de "servicios privados o con fines de lucro" | Concepto archivado; decisión registrada en ESTADO.md |
| 3 | Fase 3 | arquitecto | ADR-0001 (stack), ADR-0002 (puerto con `ContingencySource`, `DocumentSource`/manual, `DianPortalSource`), ADR-0003 (modo asistido); regla de mantenimiento basada en el 302 observado | Revisión de seguridad |
| 4 | Fase 4 | desarrollador-python | Dominio, validadores, lote, `ContingencySource`, Excel | Unitarias offline, cobertura ≥ 85 % |
| 5 | Fase 4 | ingeniero-rpa | `DianPortalSource` con detección de mantenimiento (fixture: página de redirección/imagen) y de desafío; selectores **[PENDIENTE]** → `ESTRUCTURA_CAMBIADA` mientras no existan | Fixtures locales; nunca el portal real |
| 6 | Cuando C-1 vuelva | Humano + investigador-dian | Protocolo de 05 (≤ 5 consultas autorizadas), snapshot sanitizado, `selectors.yaml` | Registro en 05 |
| 7 | Fase 5 | ingeniero-pruebas | T-54: prueba manual controlada (≤ 10) con aprobación | Informe de laboratorio |

## 11. Fuentes

Todas consultadas el **2026-10-09** (America/Bogota) salvo indicación. Fecha de publicación cuando se conoce.

| # | Fuente | URL | Fecha publicación / nota |
|---|---|---|---|
| F1 | DIAN — Consulte su estado RUT (observación en navegador) | https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces | Observado 2026-10-09 14:20:55 |
| F2 | DIAN — Imagen de mantenimiento | https://www.dian.gov.co/impuestos/RUT/PublishingImages/Mantenimiento-Consulta-RUT.jpg | Sin fecha |
| F3 | DIAN — Trámites RUT | https://www.dian.gov.co/tramitesservicios/tramites-y-servicios/tributarios/Paginas/RUT.aspx | "Última actualización" en blanco |
| F4 | DIAN — Consultas RUT | https://www.dian.gov.co/impuestos/RUT/Paginas/Consultas-RUT.aspx | En blanco |
| F5 | DIAN — Otros servicios informáticos | https://www.dian.gov.co/Transaccional/Paginas/OtrosServicios.aspx | En blanco |
| F6 | DIAN — RUT sin correo electrónico | https://www.dian.gov.co/tramitesservicios/Paginas/RUT-sin-correo-electronico.aspx | En blanco |
| F7 | DIAN — Anexo 1 Catálogo de servicios de intercambio de información | https://www.dian.gov.co/dian/Documents/Anexo-1-Catalogo-Servicios-Intercambio-Informacion.pdf | PDF creado 2021-04-16 |
| F8 | DIAN — Políticas de privacidad y términos de uso | https://www.dian.gov.co/Paginas/Privacidad.aspx | En blanco |
| F9 | DIAN — Protección de datos personales | https://www.dian.gov.co/atencionciudadano/Seguridad-de-la-Informacion/Paginas/Proteccion-de-datos-personales.aspx | Vía buscador |
| F10 | Circular DIAN 000001 de 2019 (política de tratamiento) | https://normograma.dian.gov.co/dian/compilacion/docs/circular_dian_0001_2019.htm | 2019-01-25 (vía buscador) |
| F11 | Oficio DIAN 1350 de 2019 | https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_1350_2019.htm | 2019-12-03 |
| F12 | Oficio DIAN 10720 de 2016 | https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_10720_2016.htm | 2016-05-04 |
| F13 | Concepto DIAN 45086 de 1999 (transcribe el ET art. 583) | https://normograma.dian.gov.co/dian/compilacion/docs/concepto_tributario_dian_0045086_1999.htm | 1999-05-11 |
| F14 | Resolución DIAN 000202 de 2025 | https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0202_2025.htm | 2025-03-31 (D.O. 53.076, 2025-04-01) |
| F15 | Resolución DIAN 227 de 2025 (modifica la anterior; contenido no verificado) | https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0227_2025.htm | 2025-09-23 |
| F16 | Ley 1581 de 2012 | https://normograma.dian.gov.co/dian/compilacion/docs/ley_1581_2012.htm | 2012-10-17 |
| F17 | DIAN — Guía de herramienta para el consumo de web services (FE) | https://www.dian.gov.co/impuestos/factura-electronica/Documents/Guia-Herramienta-para-el-Consumo-de-Web-Services.pdf | PDF modificado 2025-04-09 |
| F18 | DIAN — Paso a paso de radicación de PQRS 2025 | https://www.dian.gov.co/atencionciudadano/contactenos/Denuncias/Paso-a-paso-Radicacion-PQRS-2025.pdf | 2025 |
| F19 | Función Pública SUIT — Consulta del estado del RUT | https://visorsuit.funcionpublica.gov.co/auth/visor?fi=76849 | No renderizable por WebFetch; contenido vía buscador |
| F20 | Kontalid — Consulta estado RUT masiva | https://www.kontalid.com/consulta-estado-rut-dian-masiva/ | Declara actualización a marzo de 2025 |
| F21 | Kontalid — Consulta terceros DIAN | https://www.kontalid.com/info/consulta-terceros-dian/ | "Actualizado el 19 febrero, 2024" |
| F22 | ConsultorContable — Verificador de RUT | https://www.consultorcontable.com/verificador-de-rut/ | Comentarios 2025-05 a 2026-09 |
| F23 | Actualícese — Validador de terceros 2026 | https://actualicese.com/producto/aplicativo-para-consulta-masiva-de-terceros-en-la-dian-2026/ | © 2026 |
| F24 | INCP — La DIAN implementa nuevo servicio para la generación de facturas electrónicas | https://incp.org.co/publicaciones/infoincp-publicaciones/impuestos/2025/04/la-dian-implementa-nuevo-servicio-para-la-generacion-de-facturas-electronicas/ | 2025-04 (fuente secundaria del Comunicado DIAN 026/2025) |
| F25 | Enter.co — DIAN restablece servicios (falla del 2026-10-06) | https://enter.co/empresas/dian-restablece-servicios-falla-plazos-declarar | Contexto, secundaria |
| F26 | Normas citadas **sin abrir el texto en esta sesión** (verificar en normograma.dian.gov.co antes de un uso formal): ET arts. 555-2 y 584; D.L. 19/2012 art. 63; Ley 1437/2011 art. 27; Ley 1581/2012 art. 9 (misma fuente F16, no transcrito); Decreto 1377/2013 (compilado en el Decreto 1074/2015); Ley 1755/2015 art. 14; RNBD (SIC) | https://normograma.dian.gov.co/dian/ | [PENDIENTE] verificación del texto vigente |
