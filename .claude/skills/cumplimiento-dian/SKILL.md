---
name: cumplimiento-dian
description: Reglas de cumplimiento para automatizar consultas a la DIAN - qué está permitido y prohibido (captcha, Cloudflare Turnstile, endpoints internos, ritmo), alternativas A-F a evaluar (servicio oficial, API, validación documental, proveedor, RPA, contingencia) y cómo documentar evidencia. Usar en investigación, diseño, desarrollo del adaptador y revisiones de seguridad.
---

# Cumplimiento al automatizar consultas a la DIAN

## Permitido
- Automatizar en un navegador **visible** las mismas acciones que haría una persona en un canal público, a ritmo humano, si las condiciones de uso no lo prohíben.
- Detectar la presencia de un desafío de seguridad y **ceder el control al operador**.
- Usar canales oficiales documentados (servicios, API, interoperabilidad) con las credenciales y permisos que otorgue la entidad.

## Prohibido (bloqueado por hooks y revisiones)
- Resolver o saltar CAPTCHA / Cloudflare Turnstile / reCAPTCHA automáticamente o mediante terceros (2captcha, anti-captcha, capsolver, capmonster, deathbycaptcha…).
- Ocultar la automatización: `playwright-stealth`, `puppeteer-extra-plugin-stealth`, `undetected-chromedriver`, `selenium-stealth`, parches a `navigator.webdriver`, rotación de huellas/user-agent/proxies.
- Llamar endpoints internos (JSF/AJAX, `javax.faces.ViewState` reproducido por HTTP, etc.) descubiertos en el tráfico de red sin autorización documentada.
- Consultas masivas sin finalidad y base legal; paralelismo contra el portal.
- Seguir insistiendo tras bloqueos (2 bloqueos seguidos = detener el lote).

## Alternativas que se deben evaluar (Fase 2)
| Id | Alternativa | Pregunta clave |
|---|---|---|
| A | Servicio oficial de consulta | ¿Existe hoy, está disponible, qué devuelve, quién puede usarlo? |
| B | API / servicio web / interoperabilidad oficial | ¿Documentación oficial, autenticación, convenio, costo, condiciones? |
| C | Validación documental (copia del RUT entregada por el tercero) | ¿Qué campos se verifican en el documento y cuáles exigen consulta a la DIAN? ¿Vigencia? |
| D | Proveedor comercial | ¿Consulta realmente a la DIAN? ¿Origen, actualidad, contrato, costo, base legal, API? |
| E | RPA + scraping del canal público | Solo si hay interfaz funcional y no se evaden controles |
| F | Contingencia manual/semiautomática | Trazabilidad: fuente, fecha, responsable |

## Cómo documentar evidencia
Cada hallazgo: afirmación · fuente (URL) · fecha de publicación o de consulta (America/Bogota) · clasificación (Confirmado/Pendiente/Descartado) · cita breve.
Distinguir siempre: inscripción/actualización del RUT ≠ copia del RUT del titular ≠ consulta del estado por un tercero.

## Ritmo por defecto
- 1 consulta a la vez; `MIN_DELAY_BETWEEN_QUERIES_S=5` (no configurable por debajo de 3).
- Reintentos solo para `PORTAL_NO_DISPONIBLE`, `TIEMPO_AGOTADO`, `SESION_VENCIDA`, con backoff.
- Desafío de seguridad: esperar al operador `HUMAN_CHALLENGE_TIMEOUT_S` (por defecto 120 s) → si no, `REQUIERE_INTERVENCION_HUMANA`.
