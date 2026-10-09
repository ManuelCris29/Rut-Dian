# 01 — Estado de la URL original (T-10)

> Agente: investigador-dian · Fecha de elaboración: 2026-10-09 · Zona horaria: America/Bogota (UTC-5)

## URL verificada

`https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces`
(servicio oficial "Consulte su estado RUT"; enlazado desde la página oficial de trámites RUT de la DIAN; ver `02-canales-oficiales.md`).

## Comprobación 1 — navegador real (Playwright MCP, Chromium, sin modo stealth)

| Campo | Valor |
|---|---|
| Fecha/hora | **2026-10-09 14:20:55 America/Bogota** (19:20:55 UTC) |
| Método | Navegación de observación pasiva (1 de 5 permitidas). No se digitó ningún número ni se interactuó con formularios. |
| Respuesta de la URL | **HTTP 302 Moved Temporarily** |
| Destino de la redirección | `https://www.dian.gov.co/impuestos/RUT/PublishingImages/Mantenimiento-Consulta-RUT.jpg` → **HTTP 200** (imagen 1920×1080) |
| Consola | 1 error: `favicon.ico` 404 en www.dian.gov.co (irrelevante) |
| Captcha / Turnstile | **No observado** (no se llega a cargar ningún formulario) |
| Formulario | **No existe**: la página servida es solo una imagen |

**Texto de la imagen oficial (transcripción literal):**
> "Nos encontramos realizando ajustes tecnológicos sobre la funcionalidad de **Consulta estado RUT,** por lo que el servicio permanecerá **temporalmente fuera de operación** mientras culminan las actividades programadas. Gracias por su comprensión." — logo DIAN · www.dian.gov.co

La imagen **no indica fecha de inicio ni fecha estimada de restablecimiento**.

Captura: guardada solo localmente en `.playwright-mcp/mantenimiento.png` (carpeta en `.gitignore`; contiene únicamente la imagen pública de la DIAN, sin datos personales). **No se versiona.**

## Comprobación 2 — terminal (HTTP directo)

Intento de `curl` a la URL a las ~14:20 America/Bogota: **bloqueado por el hook del proyecto**
(`bloquear_evasion.py`: "no se consulta la DIAN por HTTP directo desde la terminal"). Comportamiento esperado; no se reintentó.

> **Constancia:** el acceso HTTP directo a dominios de la DIAN (curl, wget, requests, etc.) **no debe reintentarse** ni por agentes ni por personas como parte del proyecto. La observación del portal se hace solo en un navegador visible (Playwright MCP o el navegador del humano), con las reglas de CLAUDE.md §3.

## Clasificación

| # | Hallazgo | Clasificación |
|---|---|---|
| U-1 | La URL oficial responde 302 hacia la imagen oficial de mantenimiento de la DIAN | **[CONFIRMADO]** 2026-10-09 14:20:55 COT, navegador real |
| U-2 | El servicio "Consulta estado RUT" está "temporalmente fuera de operación" por "ajustes tecnológicos" | **[CONFIRMADO]** (texto oficial en dian.gov.co) |
| U-3 | Fecha de inicio del mantenimiento / fecha de restablecimiento | **[PENDIENTE]** — no publicada en la imagen ni en las páginas RUT consultadas; preguntar en PQRSD (06) |
| U-4 | Existencia de captcha/Cloudflare Turnstile en el formulario | **[PENDIENTE]** — imposible observar mientras dure el mantenimiento (ver 05) |
| U-5 | Hallazgo H1 de SPEC §3 | Pasa de [PENDIENTE] a **[CONFIRMADO]** |

## Contexto relacionado (no es la causa confirmada)

- La DIAN informó una afectación temporal de servicios tecnológicos el 2026-10-06 por una falla eléctrica externa y su posterior restablecimiento (Comunicado 129, reseñado por medios). Fuentes secundarias: https://enter.co/empresas/dian-restablece-servicios-falla-plazos-declarar , https://pymenoticias.com/post/caida-servicios-dian-falla-electrica-pymes (consulta 2026-10-09). **No** se relaciona con el mantenimiento observado: la imagen habla de "ajustes tecnológicos programados". [PENDIENTE] relación.
- Comentarios de un proveedor y de usuarios indican indisponibilidad/intermitencia de "Estado del RUT" desde mayo de 2026 (ver 04). Fuente no oficial.

## Qué debe verificar el humano

1. Abrir la URL en su navegador habitual (Chrome/Edge), **sin digitar ningún número**, y anotar fecha/hora, si aparece la imagen de mantenimiento o el formulario y, si aparece el formulario, si se muestra un desafío (casilla, Turnstile, imagen).
2. Repetir la comprobación una vez por semana hasta que la DIAN restablezca el servicio o responda la PQRSD; registrar cada intento en la tabla siguiente.

| Fecha/hora (COT) | Quién | Resultado (mantenimiento / formulario / error) | ¿Desafío visible? Tipo | Observación |
|---|---|---|---|---|
| 2026-10-09 14:20:55 | investigador-dian (Playwright) | Mantenimiento (302 → imagen) | No aplica | Sin formulario |
| | | | | |
