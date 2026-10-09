# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Consulta automatizada del estado del RUT (DIAN)

Este archivo es la memoria del proyecto. Lo lee cada sesión de Claude Code y cada subagente.
Las reglas aquí escritas **no son sugerencias**: si una tarea las contradice, detente y pregunta.

## 1. Qué estamos construyendo

Una aplicación que recibe números de identificación (cédula / NIT), consulta el estado del RUT
a través de un **canal oficial o autorizado** de la DIAN, extrae solo los campos necesarios y los
entrega en el formato que defina el negocio (Excel / CSV / JSON), con trazabilidad y manejo de errores.

- Especificación maestra: @specs/SPEC.md
- Estado vivo del proyecto (fase, decisiones, riesgos, pendientes): @docs/ESTADO.md
- Backlog de tareas: `specs/tareas.md`
- Decisiones de arquitectura: `docs/adr/`

## 2. Rol de la sesión principal: ORQUESTADOR

La sesión principal **no escribe código de producción directamente**. Coordina y delega:

| Fase | Agente responsable | Apoyo |
|---|---|---|
| 1. Requisitos | `analista-requisitos` | `documentador` |
| 2. Viabilidad | `investigador-dian` | `revisor-seguridad` |
| 3. Diseño | `arquitecto` | `revisor-seguridad` |
| 4. Desarrollo | `desarrollador-python`, `ingeniero-rpa` | `revisor-codigo` |
| 5. Pruebas | `ingeniero-pruebas` | `revisor-seguridad` |
| 6. Producción | `ingeniero-devops` | `documentador` |

Reglas del orquestador:
1. Antes de actuar, lee `docs/ESTADO.md` y confirma la fase actual.
2. **Nunca avances de fase sin pasar el gate** (`/cerrar-fase`) y sin aprobación explícita del humano.
3. Lanza en paralelo solo tareas independientes (p. ej. revisión de código + revisión de seguridad).
4. Los subagentes no pueden lanzar otros subagentes: la coordinación siempre vuelve aquí.
5. Tras cada tarea, actualiza `docs/ESTADO.md` y `specs/tareas.md`.
6. Si falta información de negocio, **pregunta**; registra supuestos como `SUPUESTO:` en ESTADO.md.

## 3. Reglas no negociables (cumplimiento)

- **No evadir** CAPTCHA, Cloudflare Turnstile, autenticación, límites de tasa ni mecanismos antibot.
  Prohibido: plugins *stealth*, `undetected-chromedriver`, servicios de resolución de captcha
  (2captcha, anticaptcha, capsolver…), rotación de proxies/huellas, falsificar user-agent para ocultar automatización.
  Un hook (`.claude/hooks/bloquear_evasion.py`) bloquea estos patrones.
- Si aparece un desafío de seguridad → el sistema **se detiene** y marca `REQUIERE_INTERVENCION_HUMANA`.
- No usar endpoints internos no documentados de la DIAN.
- No afirmar que el portal permite automatización sin evidencia (fuente + fecha) en `docs/investigacion/`.
- No inventar selectores, campos, APIs, costos ni resultados de pruebas. Todo selector sale de un
  snapshot real documentado en `docs/investigacion/`.
- Las pruebas automatizadas **nunca** golpean el portal real: usan fixtures HTML locales.
  Las pruebas contra el portal real son manuales, marcadas `@pytest.mark.portal_real` y requieren aprobación.
- Ritmo responsable: máximo 1 consulta a la vez, pausa configurable (≥ 5 s por defecto) entre consultas.

## 4. Protección de datos (Ley 1581 de 2012 y confidencialidad tributaria)

- Los números de identificación son datos personales. **En logs siempre enmascarados**: `******4321`.
- Nunca guardar capturas de pantalla, HTML ni resultados con datos reales dentro del repositorio.
  `data/`, `output/` y `logs/` están en `.gitignore`.
- Fixtures de prueba: solo identificaciones ficticias de la lista blanca de `tests/fixtures/README.md`.
- Ver skill `proteccion-datos-co`.

## 5. Stack (propuesto — se confirma al cerrar la Fase 2, ver `docs/adr/0001-stack-tecnologico.md`)

- Python 3.12 · gestor `uv` · Playwright para Python (navegador **visible**, sin modo stealth)
- Pydantic v2 + pydantic-settings · Typer (CLI) · openpyxl / csv / json para exportar
- pytest + pytest-playwright · ruff (lint + formato) · mypy (estricto en `domain/`)
- python-stdnum (`stdnum.co.nit`) para validar NIT/dígito de verificación — verificar API con Context7 antes de usar.
- CI: GitHub Actions (lint + tests offline).

**Antes de usar cualquier librería, consulta su documentación vigente con Context7**
(`resolve-library-id` → `query-docs`). No confíes en la memoria del modelo para APIs.

## 6. Convenciones de código

- Identificadores (variables, funciones, clases, archivos) **en inglés**; comentarios, docstrings,
  mensajes al usuario y documentación **en español**.
- Tipado estricto: prohibido `Any` salvo justificación en comentario. Sin `# type: ignore` sin motivo.
- Funciones pequeñas, una responsabilidad. Arquitectura por capas (ver skill `python-arquitectura`,
  paquete `src/rut_checker/`): dependencias `cli → application → ports ← adapters`; `domain` solo usa
  stdlib, pydantic y stdnum (nunca `adapters` ni Playwright). DI manual en `cli.py` (`build_service(settings)`).
  `RUT_SOURCE=fake` selecciona `FakeSource` para trabajar sin portal.
- La traducción excepción → `QueryStatus` vive en un único lugar: `BatchQueryService`.
- Selectores del portal en `config/selectors.yaml`, no en código; si falta uno obligatorio → `ESTRUCTURA_CAMBIADA`.
- Errores explícitos: excepciones de dominio propias + `QueryStatus` (ver `specs/excepciones.md`).
- Configuración por variables de entorno (`.env`, plantilla en `.env.example`). Nunca leer ni editar `.env` real.
- TDD: primero la prueba que falla, luego el código. Cada tarea termina con `uv run pytest` y `uv run ruff check` en verde.

## 7. Comandos del proyecto

| Comando | Para qué |
|---|---|
| `/iniciar` | Arranque: verifica entorno, lee estado y ejecuta la fase actual |
| `/fase <n>` | Ejecuta la fase *n* con sus agentes |
| `/investigar-dian` | Fase 2: investigación de canales oficiales y viabilidad |
| `/implementar <T-xx>` | Implementa una tarea del backlog con ciclo TDD |
| `/revisar` | Revisión de código + seguridad en paralelo |
| `/cerrar-fase` | Gate de calidad de la fase actual y solicitud de aprobación |
| `/estado` | Resumen del avance, riesgos y pendientes |

Comandos de desarrollo (cuando exista `pyproject.toml`):
```bash
uv sync                       # instalar dependencias
uv run playwright install chromium
uv run pytest -m "not portal_real"
uv run pytest tests/unit/test_validators.py::test_name   # una sola prueba
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run rut-checker --help
```

## 8. Guardarraíles activos (hooks) — qué esperar al trabajar

Los hooks corren con `uv run --no-project`: sin `uv` instalado quedan **desactivados en silencio**.
- `.claude/hooks/` y `.claude/settings.json` no se pueden editar (solo el humano); propón el cambio en la respuesta.
- En `src/` y `tests/`, cualquier literal entre comillas de 6–10 dígitos que no esté en la lista blanca
  (`tests/fixtures/README.md`: `1000000xxx`, `9000000xx[x]`, `1234567890`, `123456789`, `12345678`) bloquea la escritura.
- En `src/`, una llamada `logger.*(...)` con `identification`/`cedula`/`nit`/`id_number`… sin `mask` en los argumentos se bloquea.
- Tras cada Write/Edit de `.py` se aplica `ruff format` + `ruff check --fix` (el archivo puede cambiar tras editarlo).
- Al terminar (Stop), si cambió `src/` o `tests/` desde el último verde, corre `pytest -x -m "not portal_real"`;
  si falla, hay que corregir o marcar la tarea `BLOQUEADA` en `specs/tareas.md`.
