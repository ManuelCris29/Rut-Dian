# ADR-0003 — Modo asistido ante desafíos de seguridad

- **Estado:** ACEPTADO (2026-10-09) — observaciones de `revisor-seguridad` (APROBADO CON OBSERVACIONES,
  0 bloqueantes) y decisión D-4 del usuario incorporadas. Sujeto a ratificación en el gate de Fase 3.
- **Fecha:** 2026-10-09
- **Decisores:** arquitecto (propuesta), usuario (D-4, D-5), revisor-seguridad (observaciones 3, 5, 6, 12)
- **Relacionados:** ADR-0001, ADR-0002, CLAUDE.md §3, skill `cumplimiento-dian`, `specs/excepciones.md`,
  INFORME-VIABILIDAD §7 (V-02, V-07, V-08) y §9, `docs/investigacion/05-analisis-tecnico.md` §3–§4

## Contexto

- Proveedores reportan "Cloudflare o Captcha" en C-1 [PENDIENTE]; el tipo real de desafío **no se ha
  observado** (05 §3, T-14 BLOQUEADA). No se sabe si aparece al cargar, al enviar, por sesión o nunca.
- Reglas no negociables: no resolver, saltar ni ocultar la automatización frente a CAPTCHA/Turnstile;
  ante un desafío el sistema **se detiene** y cede el control → `REQUIERE_INTERVENCION_HUMANA` si no se
  resuelve a tiempo (CLAUDE.md §3; RF-10). El negocio aceptó el modo asistido (requisitos #9).
- Bloqueo detectado 2 veces seguidas → el lote se detiene (excepciones.md).
- Este ADR solo aplica cuando `DianPortalSource` está habilitado (ADR-0002 §3). Hoy no lo está.

## Alternativas

| # | Alternativa | Veredicto |
|---|---|---|
| 1 | Resolver o saltar el desafío (servicios de terceros, *stealth*, cookies de liberación, manipulación del navegador) | **Prohibida** (CLAUDE.md §3; hook `bloquear_evasion.py`) |
| 2 | Detenerse siempre sin esperar al operador | Cumple, pero desperdicia el modo asistido aprobado; cada desafío = fila perdida |
| 3 | `page.pause()` (Playwright Inspector) | Herramienta de depuración: abre el Inspector, depende de modo debug y no tiene timeout controlado → descartada |
| 4 | **Detectar → avisar al operador → esperar pasivamente con timeout a que aparezca el elemento esperado → si vence, `REQUIERE_INTERVENCION_HUMANA`** | **Elegida** |
| 5 | Esperar y además "ayudar" (clic programático en la casilla, foco al widget, scroll al iframe) | **Prohibida**: interactuar con el widget es intentar resolverlo |
| 6 | Ante desafío/bloqueo, recrear contexto o página, o limpiar cookies, para "empezar de cero" | **Prohibida**: es una forma de eludir el control |

## Decisión

### 1. Dónde vive cada responsabilidad

| Responsabilidad | Componente | Motivo |
|---|---|---|
| Detectar mantenimiento / desafío / bloqueo / estructura | `adapters/dian_portal/detection.py` | Necesita la página (Playwright solo en el adaptador) |
| Avisar al operador y esperar la resolución | `DianPortalSource` usando `OperatorPort.notify(...)` | Solo el adaptador posee la `Page` sobre la que se espera |
| Traducir excepciones de Playwright a excepciones de dominio con mensaje genérico | `DianPortalSource` | No filtrar textos de terceros (observación 3) |
| Traducir a `QueryStatus`, contar bloqueos seguidos, preguntar "¿continuar el lote?" y detener | `BatchQueryService` | Único lugar de traducción (CLAUDE.md §6) |

Puerto hacia el operador (`src/rut_checker/ports/operator.py`):

```python
class OperatorPort(Protocol):
    def notify(self, message: str) -> None: ...  # mensaje sin id completo
    def confirm_continue(self, message: str) -> bool: ...  # False si no hay terminal interactiva
```

Implementaciones: `ConsoleOperator` (Typer: `typer.echo(..., err=True)`, `typer.confirm`) y, en pruebas,
un doble programable.

### 2. Orden de detección (tras cada `goto` y tras cada envío)

1. **Mantenimiento** → `PortalUnavailable`. Regla basada en el hecho observado (05 §4.1): la URL final
   no es la del formulario **o** contiene un marcador de `detection.maintenance_url_markers`
   (hoy: `Mantenimiento-Consulta-RUT.jpg`, [CONFIRMADO 2026-10-09]). También `response.status ≥ 500`
   y errores de red de `page.goto` (Playwright no lanza por códigos HTTP de error; se lee `response.status`).
2. **Desafío** → marcadores `detection.challenge_markers` de `selectors.yaml` evaluados con
   `locator.is_visible()` (no espera) **sobre el DOM principal**. Hoy la lista es **[PENDIENTE T-14]**.
3. **Bloqueo explícito** (página de límite/denegación) → `detection.block_markers` **[PENDIENTE T-14]**
   → `AccessBlocked`. Además, `response.status` **403 o 429** → `AccessBlocked` sin depender de los
   marcadores (cuenta para la regla de 2 bloqueos seguidos).
4. **Elemento esperado** (formulario o resultado/"sin resultado") con
   `wait_for(state="visible", timeout=RUT_NAVIGATION_TIMEOUT_S*1000)` → `PlaywrightTimeoutError` →
   `QueryTimeout`.
5. **Estructura**: si la página cargó pero falta un selector obligatorio → `StructureChanged`.
   **Red de seguridad:** si no se reconoce ni mantenimiento, ni desafío, ni bloqueo, ni el elemento
   esperado, el resultado es `StructureChanged` (detiene el lote), **nunca** un dato vacío ni un
   reintento ciego. Un desafío no catalogado termina así en una parada segura.

**Desviación implementada en T-38 (orden de mantenimiento).** El paso 1 se divide: (1a) marcador de
URL de mantenimiento o URL final distinta de la del formulario (`form_url`) → `PortalUnavailable`;
luego el desafío (paso 2); después `response.status >= 500` → `PortalUnavailable`; luego el bloqueo
(paso 3). Motivo: un desafío servido con 503 sigue siendo un desafío y debe ceder el control a la
persona, no reintentarse como mantenimiento. Además, `check_page` espera de forma pasiva (un solo
`wait_for` sobre elemento esperado, host del desafío o marcador de bloqueo) con un tiempo que fija
quien llama (solo cuentan coincidencias visibles; `Locator.filter(visible=True)`, Playwright >= 1.51).
**Decisión del usuario 2026-10-10:** al agotarse la espera pasiva no se lanza `QueryTimeout`: la
página se reclasifica; un desafío o bloqueo detectados siguen ganando (`HumanInterventionRequired`
o `AccessBlocked`) y, si no se reconoce nada o aparece un tipo no esperado (p. ej. el formulario otra
vez tras enviar), el resultado es `StructureChanged` (`ESTRUCTURA_CAMBIADA`, sin reintento ciego).
`QueryTimeout` queda solo para tiempos agotados de `goto`, `fill` o carga (§2.4 y §2.5 se leen con
esta precisión). Los selectores no admiten `>>`, `internal:`, `frame` ni prefijos de
motor (`SelectorsReason.FORBIDDEN_SELECTOR_SYNTAX`), para que ningún valor del YAML pueda entrar al
frame del desafío.

### 3. Pausa asistida (cuando el paso 2 detecta un desafío)

1. Registrar evento `challenge_detected` (id enmascarado, `row_index`, `attempt`).
2. `OperatorPort.notify("Se detectó una verificación de seguridad del portal. Resuélvala en la
   ventana del navegador. Esperando hasta {N} s… (fila {row_index})")`. El aviso lleva solo el número de fila, no la identificación (ni enmascarada);
   lo mismo vale para la pregunta `confirm_continue` del servicio (§4).
3. Esperar **pasivamente** a que el elemento esperado sea visible:
   `expected.wait_for(state="visible", timeout=RUT_HUMAN_CHALLENGE_TIMEOUT_S*1000)`.
4. Si aparece → evento `challenge_resolved` (con `duration_ms`) y se continúa en el paso 3/4 del orden
   de detección. Si en la **misma** consulta vuelve a aparecer un desafío → no hay segunda pausa:
   `HumanInterventionRequired`.
5. Si vence → evento `challenge_timeout` → `HumanInterventionRequired`.

**Permitido y prohibido durante la detección y la pausa:**

| Permitido | Prohibido |
|---|---|
| `is_visible()` sobre el **elemento host** del iframe/widget en el DOM principal (detectar que existe) | `frame_locator`, `content_frame` o cualquier acción o lectura **dentro** del frame del desafío |
| `wait_for` pasivo del elemento esperado del formulario/resultado | Clic, escritura, foco, *hover*, *scroll* o `evaluate` sobre el desafío |
| Mantener el mismo contexto, página y cookies | **Recrear** contexto o página, recargar, o **limpiar cookies** ante desafío o bloqueo |
| Abrir **página nueva** solo ante `SessionExpired` (único caso) | `new_context` fuera del inicio del lote |

Navegador: `chromium.launch(headless=False)` obligatorio cuando `RUT_SOURCE=dian_portal`.
El adaptador (T-48/T-49) fija `headless=False` en código; no lo toma de `RUT_HEADLESS` (que además `ensure_portal_enabled` exige en `false`).

**Prueba de arquitectura** (`ast`, T-30 crea la base y T-49 la extiende): falla si en
`src/rut_checker/adapters/dian_portal/` aparecen `user_agent`, `proxy`, `args`, `ignore_default_args`,
`add_init_script`, `extra_http_headers`, `route` (en código de producción), `ignore_https_errors`,
`clear_cookies`, `frame_locator`, `content_frame`, `pause`, `tracing`, `record_video_dir`,
`record_har_path`, `screenshot`, o `new_context` fuera de la función de inicio del lote
(observaciones 2, 5, 12). Tampoco se permite `DEBUG=pw:api` en la configuración ni en la CI.

### 4. Política del servicio

| Excepción | `QueryStatus` | Reintento | Efecto en el lote |
|---|---|---|---|
| `HumanInterventionRequired` | `REQUIERE_INTERVENCION_HUMANA` | **Nunca automático** | Cuenta como **bloqueo**. 1.º: `OperatorPort.confirm_continue("¿Continuar con el lote?")`; si responde no (o no hay terminal) → detener. 2.º seguido → detener sin preguntar |
| `AccessBlocked` | `REQUIERE_INTERVENCION_HUMANA` | Nunca | Igual que la fila anterior |
| Desafío resuelto por el operador | (el de la consulta) | — | No cuenta como bloqueo |

- El contador de bloqueos seguidos se reinicia con cualquier `EXITOSA` o `SIN_RESULTADOS`.
- Al detener el lote, las filas restantes se resuelven con la fuente de respaldo (ADR-0002 §4) con
  observación "Lote detenido: verificación de seguridad no resuelta".
- El ritmo (`RUT_MIN_DELAY_BETWEEN_QUERIES_S`, ≥ 3, por defecto 5) se aplica igual después de una pausa.

### 5. Configuración

| Variable | Por defecto | Límites (validador) |
|---|---|---|
| `RUT_HUMAN_CHALLENGE_TIMEOUT_S` | 120 | 30 ≤ x ≤ 900 |
| `RUT_HEADLESS` | `false` | debe ser `false` si `RUT_SOURCE=dian_portal` |
| Bloqueos seguidos para detener | 2 | **constante** (regla de cumplimiento) |

### 6. Pruebas (offline, nunca el portal real)

**Guard de red (observación 6):** fixture `autouse` en `tests/conftest.py` que, en toda prueba no
marcada `portal_real`, (1) registra `context.route("**/*", ...)` en los contextos de Playwright de prueba
y **aborta y hace fallar** cualquier petición a un host `*.dian.gov.co`, y (2) bloquea a nivel de socket
las conexiones salientes que no sean `127.0.0.1`/`localhost`. `DianPortalSource` recibe `base_url` de un
servidor HTTP local en pruebas. La CI no define variables `RUT_*` reales.

**Fixtures sintéticos de mecanismo (D-4, aprobado con condiciones):**
- Solo en `tests/fixtures/html/sintetico/`; nombres distintos a los reales (p. ej.
  `mecanismo_desafio_sin_resolver.html`, `mecanismo_desafio_resuelto.html`, `mecanismo_desconocido.html`).
- Cabecera "SINTÉTICO — no representa el portal de la DIAN" **en un comentario HTML y como texto visible**.
- Sin textos, clases, ids ni rutas que imiten a la DIAN o a Cloudflare/reCAPTCHA (nada de
  `cf-turnstile`, `g-recaptcha`, logos ni textos copiados); atributos neutros como
  `data-testid="desafio-sintetico"`.
- Selectores en `tests/fixtures/selectors_test.yaml` con `synthetic: true`; el loader de producción lo
  **rechaza** (prueba en T-37).
- Solo ids de la lista blanca y "PERSONA FICTICIA UNO".
- Se cargan con `page.set_content(...)` o el servidor local, siempre bajo el guard de red.
- No se citan como evidencia del portal y **no sustituyen** G3/G4 con fixtures reales (T-48/T-51).

Casos: desafío que nunca se resuelve (→ `REQUIERE_INTERVENCION_HUMANA` con timeout corto); desafío que
un script local oculta tras unos ms y muestra el formulario (→ pausa resuelta); página desconocida
(→ `ESTRUCTURA_CAMBIADA`); el fixture registra clics/foco/entrada sobre el elemento del desafío y la
prueba exige que el registro quede vacío. Fixture de mantenimiento: servidor local que responde 302 a
una ruta terminada en `Mantenimiento-Consulta-RUT.jpg` (comportamiento observado el 2026-10-09).

## Consecuencias

- (+) Cumple CLAUDE.md §3 por construcción y lo hace verificable con la prueba de arquitectura.
- (+) Un desafío desconocido o nuevo produce una parada segura (`ESTRUCTURA_CAMBIADA`), no evasión.
- (+) Se mide "% que requieren intervención" con los eventos `challenge_*`.
- (−) Requiere operador presente frente al equipo durante lotes con E (aceptado por el negocio).
- (−) Hasta T-14 los marcadores de desafío y bloqueo están vacíos: aunque se habilitara E por error,
  la validación de selectores lo impide (ADR-0002 §3).
- (−) Si el desafío aparece en cada consulta, 200 filas pueden exigir 200 resoluciones humanas (R-02).

## Estado

ACEPTADO (2026-10-09), ratificado por el usuario en el gate de Fase 3 (2026-10-09).
