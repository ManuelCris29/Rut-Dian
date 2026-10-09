# 03 — Condiciones de uso, protección de datos y reserva tributaria (T-12)

> Agente: investigador-dian · Consultas del 2026-10-09 (14:15–14:35 America/Bogota).
> **Esto no es asesoría legal.** Las conclusiones marcadas [PENDIENTE] requieren concepto jurídico interno o respuesta de la DIAN.

## 1. Condiciones de uso del portal DIAN

Fuente: "Políticas de privacidad y términos de uso" — https://www.dian.gov.co/Paginas/Privacidad.aspx (campo "Última actualización" en blanco; consultado el 2026-10-09).

| # | Cláusula (cita breve) | Implicación para el proyecto | Clasificación |
|---|---|---|---|
| T-1 | "La utilización de esta página web y su contenido, constituyen un acuerdo legal entre quienes ingresen a este sitio" | Las condiciones obligan al operador y a cualquier robot que actúe por él | [CONFIRMADO] |
| T-2 | Compromiso del usuario: "No usar el sitio web como medio para desarrollar actividades ilegales o no autorizadas tanto en Colombia como en el exterior" | La automatización no está autorizada **expresamente**; tampoco prohibida expresamente. Zona gris → consulta formal (06) | [CONFIRMADO] texto · [PENDIENTE] interpretación |
| T-3 | Propiedad intelectual: "Las imágenes, contenidos de información y servicios virtuales que se ponen a disposición del público en este sitio web… no podrán ser utilizados para la creación o promoción de servicios privados o con fines de lucro" | **Riesgo relevante para la alternativa D** (proveedores que venden automatizaciones del portal). **Restricción del proyecto:** la herramienta es de **uso interno exclusivo de la empresa responsable del tratamiento**; no se ofrece ni se presta como servicio a terceros, a empresas del grupo ni a clientes. Aun así, el riesgo para el uso interno no es nulo | [CONFIRMADO] texto · [PENDIENTE] alcance para uso interno (PQRSD, pregunta 5) |
| T-4 | Si el usuario incumple, pierde la autorización de uso y debe "destruir inmediatamente cualquier material o información del sitio" | Riesgo operativo: obligación de borrar resultados obtenidos con un uso no conforme | [CONFIRMADO] |
| T-5 | Sin cláusulas específicas sobre robots, scraping, consultas masivas ni acceso automatizado | No hay autorización ni prohibición explícita. **No se puede afirmar que el portal permita la automatización** | [CONFIRMADO] (ausencia) |
| T-6 | Controles técnicos (captcha/Cloudflare) reportados por proveedores | La existencia de un control antibot es, en sí misma, una señal de que la DIAN no desea consultas automatizadas no asistidas. El proyecto **no** lo evade (CLAUDE.md §3) | [PENDIENTE] verificación en el portal (05) |

## 2. Política de tratamiento de datos de la DIAN

- La página "Protección de datos personales" de la DIAN identifica la **Circular 000001 del 25-01-2019** como la política de tratamiento de datos personales de la entidad: https://www.dian.gov.co/atencionciudadano/Seguridad-de-la-Informacion/Paginas/Proteccion-de-datos-personales.aspx ; texto: https://normograma.dian.gov.co/dian/compilacion/docs/circular_dian_0001_2019.htm (consulta 2026-10-09). [CONFIRMADO] existencia · [PENDIENTE] lectura completa del texto vigente.
- La Resolución 101 de 2020 asigna la función de Oficial de Protección de Datos a la Oficina de Seguridad de la Información: https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0101_2020.htm . [CONFIRMADO] (resumen del buscador).
- Esta política rige el tratamiento que hace **la DIAN**. El tratamiento que hace **nuestra empresa** con los resultados se rige por la Ley 1581/2012 y por su propia política (ver §4).

## 3. Reserva tributaria y naturaleza de la información del RUT

| # | Norma / doctrina | Cita breve | Implicación | Clasificación |
|---|---|---|---|---|
| R-1 | **Estatuto Tributario art. 583** — Reserva de la declaración. Transcrito en el Concepto DIAN 45086 de 1999-05-11: https://normograma.dian.gov.co/dian/compilacion/docs/concepto_tributario_dian_0045086_1999.htm | "La información tributaria respecto de las bases gravables y la determinación privada de los impuestos que figuren en las declaraciones tributarias, tendrá el carácter de información reservada" | El texto se refiere a **declaraciones** (bases gravables, determinación privada). La DIAN ha extendido la reserva a los ingresos reportados en el RUT (Oficio 9678, reseñado en https://cijuf.org.co/node/7953), y se reseñó un concepto de 2026 que la extendería a "la demás información que administra la DIAN" [PENDIENTE: fuente no identificada; sin número, fecha ni URL — no se usa como base de ninguna decisión]. **Si el estado del RUT y el nombre o razón social están o no cubiertos por la reserva es [PENDIENTE: concepto jurídico]**; no se asume que estén excluidos | [CONFIRMADO] contenido del art. 583 · [PENDIENTE] texto consolidado vigente (el artículo dio 404 en la compilación del ET del normograma) y alcance sobre los datos de C-1 (PQRSD, pregunta 9) |
| R-2 | **Oficio DIAN 1350 de 2019-12-03**: https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_1350_2019.htm . Marco citado o relacionado: **ET art. 555-2** (RUT), **ET art. 583** (reserva), **ET art. 584** (examen de las declaraciones), **D.L. 19/2012 art. 63** y **Ley 1437/2011 art. 27** | El RUT "no tiene el carácter de registro público y su uso se encuentra restringido a los fines de su creación"; "solo se puede compartir la información del RUT con entidades públicas y privadas, que cumplan funciones públicas". El titular puede consultar su RUT y "bajo su responsabilidad" compartirlo con terceros | **Clave**: la DIAN **no entrega** información del RUT a privados por intercambio. Legitima la **alternativa C** (el tercero entrega su propia copia). **Riesgo:** conservar y reutilizar durante 1 año el resultado de C-1 para revalidaciones podría considerarse un uso por fuera de "los fines de su creación" → [PENDIENTE: concepto jurídico] (PQRSD, pregunta 8) | [CONFIRMADO] texto del oficio · [PENDIENTE] verificación del texto vigente de los arts. 555-2 y 584 ET en el normograma (citados, no abiertos) |
| R-3 | **Oficio DIAN 10720 de 2016-05-04**: https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_10720_2016.htm | Representante legal y actividad económica: "dato personal de naturaleza pública, relacionado con el ejercicio de la profesión y la calidad de comerciante". No clasifica el **estado** del RUT | Nombre/razón social de comerciantes tiene un carácter cercano a público; el estado no está clasificado expresamente | [CONFIRMADO] texto · [PENDIENTE] clasificación del "estado del RUT" |
| R-4 | **Resolución DIAN 000202 de 2025-03-31**, art. 4 (servicio de consulta del adquiriente): https://normograma.dian.gov.co/dian/compilacion/docs/resolucion_dian_0202_2025.htm | "En ningún caso, se podrá hacer uso masivo o distribución de la información obtenida"; uso "únicamente con el propósito de expedir la factura electrónica"; "seguro y controlado uno a uno" | Muestra el criterio actual de la DIAN y la SIC: la consulta de datos del RUT por privados es **uno a uno y con finalidad estricta**. Por analogía, refuerza que la "consulta masiva" del negocio es sensible | [CONFIRMADO] |

## 4. Ley 1581 de 2012 (Protección de datos personales)

Fuente: https://normograma.dian.gov.co/dian/compilacion/docs/ley_1581_2012.htm (Ley Estatutaria del 17 de octubre de 2012; consulta 2026-10-09).

- Art. 3 lit. g — Tratamiento: "Cualquier operación o conjunto de operaciones sobre datos personales, tales como la recolección, almacenamiento, uso, circulación o supresión." → Consultar, guardar en Excel y conservar 1 año **es tratamiento**. [CONFIRMADO]
- Art. 4 lit. b — Finalidad: "El Tratamiento debe obedecer a una finalidad legítima de acuerdo con la Constitución y la Ley, la cual debe ser informada al Titular". → La finalidad aprobada (SPEC §5: vinculación/verificación de proveedores, contratistas, clientes y empleados) debe figurar en la política y en los avisos o autorizaciones que firman los terceros. [CONFIRMADO] norma · [PENDIENTE] verificar que los formatos de vinculación de la empresa lo informen.
- Art. 10 — No se requiere autorización para "Datos de naturaleza pública" ni para "Información requerida por una entidad pública…". La empresa **no** es entidad pública, y que el estado del RUT sea dato público es [PENDIENTE: concepto jurídico].
- **Criterio conservador adoptado:** se requiere la **autorización previa, expresa e informada del titular** (Ley 1581, art. 9), obtenida por un medio que permita **probarla** después. Esta autorización es **condición obligatoria** (INFORME §8, condición d) para habilitar E y para conservar los resultados de C.
- **Política de tratamiento de la empresa** (Decreto 1377 de 2013, compilado en el Decreto 1074 de 2015): debe incluir la finalidad (vinculación y verificación de proveedores, contratistas, clientes y empleados), la retención de 1 año y su eliminación, y el canal de consultas y reclamos de los titulares. [PENDIENTE] verificar que exista y que lo cubra; texto del decreto no abierto en esta sesión.
- **Registro Nacional de Bases de Datos (RNBD, SIC):** revisar si la empresa está obligada a inscribir la base y, en ese caso, actualizar la inscripción para incluir esta base o finalidad. [PENDIENTE] responsable de datos personales.
- Los empleados son personas naturales: sus datos (cédula, nombre, estado del RUT) son datos personales. Minimización: solo campos de SPEC §5. [CONFIRMADO] regla del proyecto.

## 5. Conclusiones de T-12

1. **No se encontró autorización expresa** de la DIAN para automatizar el portal público, ni prohibición expresa de robots. [CONFIRMADO]
2. Las condiciones prohíben usar los servicios virtuales "para la creación o promoción de servicios privados o con fines de lucro" → **riesgo alto para proveedores comerciales** (alternativa D) y riesgo bajo o medio para el uso interno. La herramienta será de **uso interno exclusivo** de la empresa responsable; no se ofrece a terceros, a empresas del grupo ni a clientes. [CONFIRMADO] texto · [PENDIENTE] interpretación oficial.
3. La DIAN sostiene que el RUT no es registro público y que **no comparte** información del RUT con privados mediante intercambio → no es esperable una API o convenio para esta empresa salvo un cambio normativo. [CONFIRMADO] (Oficio 1350/2019)
4. El titular sí puede compartir su RUT con terceros → la **copia del RUT entregada por el tercero** es un canal legítimo, sujeto a la autorización y la minimización de §4. [CONFIRMADO]
5. Reserva tributaria sobre los datos de C-1 y conservación durante 1 año de sus resultados: [PENDIENTE: concepto jurídico] (PQRSD, preguntas 8 y 9).
6. **Condiciones para habilitar E** (decisión del usuario del 2026-10-09; detalle en INFORME §8):
   - automatización asistida, uno a uno, a ritmo humano y sin evadir controles;
   - se habilita solo con (i) una respuesta de la DIAN no contraria, o (ii) vencido el plazo legal sin respuesta, una **aceptación de riesgo firmada** por el área jurídica o de protección de datos y **registrada con fecha en `docs/ESTADO.md`**. **El silencio de la DIAN no es autorización**;
   - además, la autorización probada de los titulares (§4).
