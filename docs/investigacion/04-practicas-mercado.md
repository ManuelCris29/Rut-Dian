# 04 — Prácticas de empresas y proveedores (T-13)

> Agente: investigador-dian · Consultas del 2026-10-09 (14:20–14:35 America/Bogota).
> Se registra **lo que cada proveedor declara**. Nada de esto prueba que su método esté autorizado por la DIAN. Sin evidencia de integraciones o acuerdos con la DIAN → `[PENDIENTE]`.

## Proveedores con página comercial

| Proveedor | Fuente (consulta 2026-10-09) | Qué declara | Fecha declarada | Lo que NO demuestra | Clasificación |
|---|---|---|---|---|---|
| **Kontalid** — Consulta Estado RUT DIAN masiva | https://www.kontalid.com/consulta-estado-rut-dian-masiva/ | "se conecta a la DIAN como una automatización de la página Consulta Estado RUT"; las macros de Excel "dejaron de funcionar" tras un cambio del captcha de la DIAN; soporte "Mientras la página de la DIAN permita realizar este tipo de automatizaciones"; incluido en planes PREMIUM y ELITE (precio solo en imágenes) | Actualizado a "la última versión de la página de la DIAN de MARZO de 2025" | Convenio con la DIAN; cómo gestiona el desafío de seguridad | [CONFIRMADO] declaración · [PENDIENTE] método y base legal |
| **Kontalid** — Consulta terceros DIAN (info) | https://www.kontalid.com/info/consulta-terceros-dian/ | "La consulta Estado RUT depende de que la DIAN tenga su servicio «Consulta Estado RUT» ACTIVO… cuando esta consulta no esta funcionando, la consulta de Kontalid tampoco funcionará"; "En ningún caso Kontalid se hace responsable por la información desplegada"; recomienda pedir el RUT actualizado | Página "Actualizado el 19 febrero, 2024"; comentario de mayo de 2025: la página de la DIAN "esta deshabilitada" | — | [CONFIRMADO] declaración |
| **ConsultorContable** — Verificador de RUT web | https://www.consultorcontable.com/verificador-de-rut/ | Es "una Extensión para los exploradores Chrome y Edge"; "no maneja bases de datos, solo consulta de forma automática"; dos modos: "Consulta SIN estado del RUT" (~1 s por tercero) y "Consulta Estado del RUT" (6–10 s), este último "no es estable" por "las restricciones que ha implementado en la página web de la DIAN con el Cloudflare o Captcha"; requiere "Que el computador valide el captcha automaticamente al ingresar al enlace oficial"; $110.000 con IVA por año; licencia "hasta la fecha que la DIAN permita la consulta"; sin devolución si la DIAN bloquea | Comentarios fechados (ver abajo) | Convenio; la fuente de la "Consulta SIN estado del RUT" | [CONFIRMADO] declaración · [PENDIENTE] método |
| **Actualícese** — Validador de terceros 2026 | https://actualicese.com/producto/aplicativo-para-consulta-masiva-de-terceros-en-la-dian-2026/ | Aplicativo web "sin instalaciones"; "Hasta 1.000 NIT por operación"; devuelve "nombre, correo electrónico y estado de proveedor ficticio"; exporta a .xlsx; $99.000 + IVA o incluido en la suscripción. **No menciona el estado del RUT** | "© 2026"; sin fecha de publicación | Fuente de los datos (que devuelva nombre y correo coincide con los datos del servicio de adquiriente, pero **no está probado**) | [CONFIRMADO] declaración · [PENDIENTE] fuente |
| **Accounter** — Verificador masivo de RUT | https://accounter.co/servicios/herramientas/verificador-masivo-de-rut-y-lector-de-eventos-de-facturas-electronicas-aplicativos-automatizados-dian (resumen del buscador) | Extensión Chrome/Edge; indica si el tercero figura en el RUT, el DV y la razón social | Sin fecha | Método | [PENDIENTE] (no se abrió la página) |
| Paquete PyPI `dian-person-rut-status` | https://pypi.org/project/dian-person-rut-status/ (versiones 0.1.7/0.1.8 indexadas) | La página no cargó con WebFetch | — | Repositorio, licencia, método | [DESCARTADO] para uso: sin auditoría posible, sin repositorio ni licencia visibles (README de investigación) |

### Comentarios fechados en ConsultorContable (evidencia de disponibilidad del canal C-1, **no oficial**)

| Fecha | Autor | Cita |
|---|---|---|
| 2025-05-13 | usuario | "la página web de la DIAN presenta intermitencia (Caída)" |
| 2025-05-14 | proveedor | "ninguna herramienta que se venda en el mercado que realice estas consultas va a funcionar" |
| 2025-08-11 | proveedor | "la página de la DIAN no permite hacer las consultas ni siquiera de forma manual" |
| 2025-12-31 | proveedor | "La página de la Dian ha estado con intermitencia" |
| 2026-05-04 | usuario | "la DIAN ya deshabilito opción de consulta del estado del RUT" |
| 2026-05-20 | proveedor | "la opción de consulta estado del RUT presenta intermitencia." |
| 2026-06-08 | proveedor | "en este momento funciona bien una de las dos" |
| 2026-09-08 | — | comentario más reciente visible en la página |

**Lectura:** los proveedores **dependen del mismo portal público** (C-1). Cuando la DIAN lo apaga o endurece el desafío, todas las herramientas fallan. **No ofrecen una fuente alternativa autorizada**; además, el que el captcha deba validarse "automáticamente" muestra que dependen de que el desafío no exija interacción. [CONFIRMADO] por sus propias declaraciones.

## ERP y software contable

| Actor | Evidencia | Clasificación |
|---|---|---|
| Alegra (proveedor tecnológico de factura electrónica) | Changelog "Nuevo servicio de consulta de información del adquiriente": https://e-provider-docs.alegra.com/changelog/nuevo-servicio-de-consulta-de-informaci%C3%B3n-del-adquiriente (título visto en el buscador, 2026-10-09) → integra el servicio C-6, cuya finalidad se limita a la facturación | [CONFIRMADO] existencia del changelog · [PENDIENTE] contenido |
| Odoo (l10n_co), The Factory HKA, LibreGestión, ITS Contable | Foros y wikis que describen el consumo del web service de adquirientes de la DIAN (https://www.odoo.com/forum/help-1/l10n-co-consumo-de-web-service-dian-para-datos-de-adquirientes-282035 ; https://felcowiki.thefactoryhka.com.co/index.php/M%C3%A9todos_Servicio_datos_adquiriente_web_soap_-_Indice_Manual_Integraci%C3%B3n_Directa ; https://www.itscontable.com/blog/consulta-nit-por-web-service-de-la-dian/) | [CONFIRMADO] que el mercado usa C-6 para facturar · No sirve para el estado del RUT ni para validación masiva (Res. 202/2025 art. 4) |
| Siigo | Blog "cómo consultar el estado del RUT" (https://www.siigo.com/blog/obligaciones-fiscales/como-consultar-el-estado-del-rut/) remite al portal público | [CONFIRMADO] remite a C-1 · sin integración propia demostrada |
| Plataformas de proveedores (portales de compras) | No se encontró evidencia pública de un canal propio; se presume solicitud de la copia del RUT al proveedor | [PENDIENTE] |

## Macros de Excel de terceros

Kontalid afirma que "las herramientas de Excel y las Macros de consulta de terceros DIAN dejaron de funcionar" tras el cambio de captcha (2025). Las macros que hacen peticiones HTTP directas al formulario JSF son, por definición, **uso de endpoints internos** → prohibido por CLAUDE.md §3; se registran solo como **riesgo**, no como alternativa. [DESCARTADO]

## Conclusión T-13

- El mercado **no tiene un canal oficial alternativo**: automatiza el portal público, con disponibilidad atada a la DIAN e inestable desde mayo de 2025. [CONFIRMADO] por declaraciones de los propios proveedores.
- Ningún proveedor declara convenio ni autorización de la DIAN. [PENDIENTE] (sin evidencia).
- Las condiciones del portal prohíben usar sus servicios virtuales "para la creación… de servicios privados o con fines de lucro" (03, T-3) → riesgo de cumplimiento al contratar un proveedor, además de la falta de presupuesto (RN-08). Alternativa D: **no recomendada**.
