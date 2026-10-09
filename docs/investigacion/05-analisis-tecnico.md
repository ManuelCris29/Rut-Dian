# 05 — Análisis técnico del canal elegible (T-14)

> Agente: investigador-dian · 2026-10-09 · America/Bogota
> Estado de la tarea: **BLOQUEADA** — el canal C-1 está en mantenimiento; no hay formulario que observar.

## 1. Canal elegible

Único canal oficial de consulta de estado por terceros: **C-1 "Consulte su estado RUT"**
`https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces` (ver 02).

## 2. Observación pasiva realizada

| # | Fecha/hora (COT) | Acción | Resultado |
|---|---|---|---|
| N-1 | 2026-10-09 14:20:55 | `browser_navigate` a la URL (Playwright MCP, Chromium visible, sin stealth) | 302 → `www.dian.gov.co/impuestos/RUT/PublishingImages/Mantenimiento-Consulta-RUT.jpg` (200). El snapshot de accesibilidad está vacío (solo imagen). |

Navegaciones usadas: **1 de 5**. No se digitó ningún número, no se envió ningún formulario y no apareció ningún desafío.
No se guardó HTML. La única captura (imagen pública de mantenimiento, sin datos personales) queda en `.playwright-mcp/` (ignorada por git).

## 3. Lo que no se pudo observar → [PENDIENTE]

| Elemento | Estado | Cómo se resolverá |
|---|---|---|
| Estructura del formulario (campos, etiquetas, botón) | [PENDIENTE] | Snapshot de accesibilidad cuando el servicio vuelva |
| Selectores (`config/selectors.yaml`) | [PENDIENTE] — **no se inventan**. Prohibido derivarlos de fuentes de terceros o de archivos web | Snapshot real, sanitizado |
| Tipo de desafío de seguridad (Cloudflare Turnstile gestionado / no interactivo / captcha de imagen / ninguno) | [PENDIENTE]. Los proveedores mencionan "Cloudflare o Captcha" (04), sin confirmar | Observación humana (protocolo §5) |
| Campos del resultado y textos de estado (p. ej., ACTIVO, CANCELADO, SUSPENDIDO) | [PENDIENTE]. La ficha SUIT habla de nombre/razón social y estado "activo - cancelado"; un proveedor menciona "activo, suspendido, cancelado" | Pruebas autorizadas (§5) |
| Mensaje de "no inscrito" / sin resultado | [PENDIENTE] | §5 |
| Expiración de sesión / ViewState, tiempos de respuesta | [PENDIENTE] | §5 (solo se registra el comportamiento visible; **no** se reproducen peticiones JSF por HTTP) |
| Límites de tasa / bloqueos | [PENDIENTE] | §5 + respuesta PQRSD |

## 4. Implicaciones de diseño (para Fase 3, ya conocidas)

1. La **detección de mantenimiento** puede basarse en un hecho observado: la URL redirige (302) a una imagen en `www.dian.gov.co/.../Mantenimiento-Consulta-RUT.jpg`. Regla candidata: "si la URL final no es la del formulario o termina en `Mantenimiento-Consulta-RUT.jpg` → `PORTAL_NO_DISPONIBLE`". [CONFIRMADO] comportamiento al 2026-10-09; puede cambiar.
2. Ante cualquier desafío → pausa asistida → `REQUIERE_INTERVENCION_HUMANA` si vence `HUMAN_CHALLENGE_TIMEOUT_S`. Nunca resolución automática. [CONFIRMADO] regla del proyecto.
3. **Riesgo registrado (no es alternativa):** el portal es una aplicación JSF (`.faces`). Cualquier reproducción de sus peticiones internas (`javax.faces.ViewState`, AJAX) por HTTP queda **prohibida**; las macros de Excel del mercado probablemente lo hacían (04). No se inspeccionó ni se documenta el tráfico.

## 5. Protocolo para el humano (≤ 5 consultas autorizadas) — ejecutar SOLO cuando el servicio vuelva

**Precondiciones**
- [ ] El servicio ya no muestra la imagen de mantenimiento (comprobar sin digitar nada).
- [ ] Hay aprobación registrada del humano responsable para esta prueba.
- [ ] Se usarán **como máximo 5 números**, propios o del equipo, con autorización de sus titulares. **Nunca** números de terceros.
- [ ] Cada titular dio **autorización escrita o por correo** para esta prueba. La prueba de la autorización se guarda **fuera del repositorio** (repositorio documental de la empresa) y en la plantilla solo se marca "sí/no".
- [ ] Los números **no** se escriben en ningún archivo del repo, chat ni log. En la plantilla solo van los **últimos 4 dígitos** (`******1234`).

**Pasos (navegador habitual, manual)**
1. Abrir la URL y anotar fecha/hora (COT) y si aparece un desafío **antes** de digitar (tipo: casilla "Verifique que es humano", Turnstile automático, imagen, ninguno).
2. Digitar el número, enviar y anotar: si apareció un desafío al enviar, tiempo hasta el resultado y etiquetas visibles del resultado (**solo las etiquetas**, p. ej. "Estado", "Razón social"; **no** los valores).
3. Para 1 de los 5: dejar la página abierta 10–15 minutos y volver a consultar; anotar si la sesión venció y qué mensaje se mostró.
4. Mensaje de "sin resultado": solo si, entre los números autorizados, hay uno de un miembro del equipo que sepa que **no** está inscrito en el RUT. **No** inventar números al azar: podrían pertenecer a un tercero real. Si no hay ninguno, queda [PENDIENTE] para T-54.
5. Pausa de al menos 30 s entre consultas. Si aparece un bloqueo o un desafío repetido, **detenerse**.
6. Snapshots para `selectors.yaml` y fixtures:
   - **Vía agente (Playwright MCP):** solo el snapshot de accesibilidad del formulario **VACÍO**, antes de digitar nada.
   - **Página de resultado:** la guarda y sanitiza **el humano, localmente y sin agente**. Debe reemplazar por marcadores: números de identificación, DV, nombres y razones sociales; **inputs ocultos**; `javax.faces.ViewState`; tokens; cookies; y URLs con parámetros. Ningún agente de IA procesa la versión sin sanitizar.
   - Antes de cualquier commit en `docs/investigacion/snapshots/`, **revisor-seguridad** revisa los archivos sanitizados.
   - Al terminar la sesión, borrar `.playwright-mcp/*.yml`, `.playwright-mcp/*.png` y `.playwright-mcp/*.log`.

**Plantilla de registro (sin datos personales)**

| # | Fecha/hora (COT) | Id enmascarado | Autorización registrada (sí/no) | Tipo (CC/NIT) | Desafío al cargar (tipo) | Desafío al enviar (tipo) | ¿Resuelto por el humano? | Tiempo hasta el resultado (s) | Etiquetas visibles del resultado | Texto de estado mostrado (genérico: ACTIVO/…) | Observación |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | ******____ | | | | | | | | | |
| 2 | | ******____ | | | | | | | | | |
| 3 | | ******____ | | | | | | | | | |
| 4 | | ******____ | | | | | | | | | |
| 5 | | ******____ | | | | | | | | | |

Si la columna "Autorización registrada" dice "no", **esa consulta no se ejecuta**.

**Preguntas que esta prueba debe responder**
- ¿El desafío aparece en cada consulta, por sesión o nunca? → define la viabilidad del modo asistido (R-02).
- ¿Cuántos segundos por consulta, incluido el desafío? → compara con la línea base de más de 3 min.
- ¿Qué etiquetas y estados exactos muestra? → RN-03 y nombres finales de SPEC §5.
