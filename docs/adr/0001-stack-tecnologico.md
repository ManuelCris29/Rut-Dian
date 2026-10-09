# ADR-0001 — Stack tecnológico

- **Estado:** ACEPTADO (modificado) — ratificado por el usuario en el gate de Fase 3 (2026-10-09). Revisión de seguridad: APROBADO CON OBSERVACIONES (2026-10-09), incorporadas
- **Fecha:** 2026-10-09 (propuesto) · 2026-10-09 (revisado tras Fase 2, T-20)
- **Decisores:** arquitecto (propuesta), usuario (aprobación en gate)
- **Relacionados:** ADR-0002 (puerto y adaptadores), ADR-0003 (modo asistido), `docs/investigacion/INFORME-VIABILIDAD.md` §5–§10

## Contexto

La versión propuesta de este ADR se condicionaba a que el informe de viabilidad concluyera que
"existe un canal oficial con interfaz web utilizable sin evadir controles". El informe (aprobado en
el gate de Fase 2) concluye otra cosa:

1. El canal C-1 "Consulte su estado RUT" está **en mantenimiento** (302 → imagen, 2026-10-09
   14:20:55 COT), sin fecha de regreso. [CONFIRMADO]
2. No hay API ni convenio para privados (B descartada) y no hay presupuesto para proveedor (D
   descartada). [CONFIRMADO]
3. La **base operativa es C + F**: registro de metadatos de la copia del RUT (≤ 30 días; el PDF nunca
   lo procesa la herramienta) + contingencia manual trazable. Ninguna de las dos necesita navegador.
4. **E (RPA asistido)** se construye detrás del puerto pero queda **deshabilitado** hasta cumplir las
   condiciones (a)–(d) de INFORME §8.
5. Condiciones que siguen vigentes: el desarrollo lo hacen agentes desde la terminal; equipo del
   operador Windows 10/11 y CI Linux (RNF-06); navegador visible y sin ocultar la automatización si E
   se habilita (RNF-02, CLAUDE.md §3).

Consecuencia: el núcleo de la aplicación (validación, lote, trazabilidad, Excel) **no depende del
navegador**. Playwright pasa de ser el centro del stack a ser la dependencia de un único adaptador
opcional.

## Alternativas

| Criterio | Power Automate Desktop | UiPath | Python + Selenium | **Python + Playwright (adaptador opcional)** | requests/httpx (HTTP directo al portal) |
|---|---|---|---|---|---|
| ¿Lo construyen y prueban agentes desde CLI? | No (editor gráfico) | Parcial (XAML, Studio) | Sí | **Sí** | Sí |
| Núcleo C + F sin navegador | No natural (todo es flujo RPA) | No natural | Sí | **Sí** (Playwright solo en `adapters/dian_portal`) | Sí |
| Pruebas offline | Muy limitado | Test Suite (licencia) | Sí | **Sí** (pytest-playwright + fixtures locales) | Sí |
| Esperas / estabilidad | Media | Alta | Esperas explícitas manuales | **Auto-wait + locators** | N/A |
| Pausa asistida en navegador visible | Sí | Sí | Sí | **Sí** (espera del locator esperado con timeout; ver ADR-0003) | **No hay navegador → descartado** |
| Licencia | Windows; desatendido con licencia | Comercial | Libre | **Libre (Apache-2.0)** | Libre |
| Riesgo de cumplimiento | Bajo | Bajo | Bajo | Bajo | **Alto**: induce a reproducir peticiones JSF internas (prohibido, 05 §4.3) → descartado |

## Decisión

**Python 3.12 + uv**, con este stack (versiones exactas fijadas en `uv.lock` en T-30; no se fijan
números de versión aquí para no inventarlos):

| Dependencia | Uso | Requisito que la justifica | Dónde se permite |
|---|---|---|---|
| pydantic v2 | Modelos de dominio inmutables, validación | RF-03, RF-05, RNF-07 | `domain`, `infra`, `adapters` |
| pydantic-settings | Configuración por variables `RUT_*` y `.env` | RNF-01, RNF-02 | `infra/settings.py` |
| python-stdnum (`stdnum.co.nit`) | DV del NIT | RF-03, RN-02 | `domain/validators.py` |
| tzdata | Zona `America/Bogota` vía `zoneinfo` en Windows (no trae base de zonas del sistema) | RNF-04, RNF-06 | transitiva de `domain`/`infra` |
| openpyxl | Leer lote `.xlsx`, escribir resultado `.xlsx` | RF-02, RF-06 | `io/` |
| defusedxml | openpyxl lo usa automáticamente si está instalado para protegerse de *billion laughs* / *quadratic blowup* al leer `.xlsx` de terceros | RNF-01 (observación de seguridad 9) | transitiva de `io/` |
| Typer | CLI `rut-checker` | RF-01, RF-02, RF-13 (CLI en vez de GUI) | `cli.py`, `adapters/console_operator.py` |
| PyYAML (`safe_load`) | Leer `config/selectors.yaml` | RNF-03 | `adapters/dian_portal/selectors.py` |
| **Playwright para Python** (API **síncrona**) | Adaptador E | RF-04, RF-10 | **solo** `adapters/dian_portal/` |
| Desarrollo: pytest, pytest-playwright, ruff, mypy | Calidad | RNF-05 | `tests/`, CI |

Reglas de empaquetado:
- Playwright y PyYAML van en un **extra opcional `portal`** (`[project.optional-dependencies]`) y en el
  grupo de desarrollo. La instalación base del operador (modo C + F) **no** necesita
  `playwright install chromium`. `build_service` importa `adapters.dian_portal` **solo** si
  `RUT_SOURCE=dian_portal` (import diferido).
- Sin dependencias de evasión (listas bloqueadas por `.claude/hooks/bloquear_evasion.py`), sin
  `user_agent` personalizado, sin proxy, sin `args` de lanzamiento que oculten la automatización.
- Sin base de datos, sin colas, sin servicio web: un proceso CLI local que lee y escribe archivos.
- Exportadores JSON/CSV: stdlib (`json`, `csv`), solo si se implementa el *Could* de RF-06 y para el
  respaldo de `ERROR_EXPORTACION`.

PAD/UiPath y Selenium: descartados para este proyecto (construido por agentes). El diseño (estados,
excepciones, selectores en YAML, specs) sigue siendo transferible si la organización exige su
plataforma RPA corporativa.

## APIs verificadas con Context7 (2026-10-09)

Fuentes: `/websites/playwright_dev_python`, `/pydantic/pydantic-settings`, `/pydantic/pydantic`,
`/websites/typer_tiangolo`, `/websites/openpyxl_readthedocs_io_en_stable`, `/arthurdejong/python-stdnum`,
`/yaml/pyyaml`. `stdnum.co.nit` no aparece en Context7 con detalle: su código se verificó en el
repositorio oficial `github.com/arthurdejong/python-stdnum/blob/master/stdnum/co/nit.py`.

| API | Lo que el diseño asume | Verificado |
|---|---|---|
| Playwright `page.get_by_label(...)`, `page.get_by_role("button", name=...)`, `page.get_by_text(...)`, `page.locator(css)` | Estrategias `label`/`role`/`text`/`css` de `selectors.yaml` | Sí (docs "Locators", API síncrona) |
| Playwright `locator.wait_for(state="visible", timeout=ms)` | Espera del formulario/resultado y de la resolución humana del desafío; `timeout` en **milisegundos**, por defecto 30000; `0` desactiva | Sí (class-locator) |
| Playwright `from playwright.sync_api import TimeoutError as PlaywrightTimeoutError` | Se traduce a `QueryTimeout` dentro del adaptador | Sí (class-timeouterror) |
| Playwright `page.set_default_timeout(ms)` | `RUT_NAVIGATION_TIMEOUT_S × 1000` | Sí (class-page) |
| Playwright `page.goto(url)` → `Response` (`response.status`); **no lanza** por códigos HTTP de error, sí por fallas de red/timeout | Detección de 5xx (`PORTAL_NO_DISPONIBLE`) se hace leyendo `response.status`, y red caída por excepción | Sí (class-page, class-response) |
| Playwright `expect(locator).to_be_visible(timeout=ms)`; `expect.set_options(timeout=...)`; timeout por defecto de aserciones 5 s | Solo en pruebas | Sí (test-assertions) |
| Playwright `locator.is_visible()` no espera | Comprobación inmediata de marcadores de mantenimiento/desafío | Sí (class-locator) |
| pydantic-settings `BaseSettings` + `SettingsConfigDict(env_prefix="RUT_", env_file=".env", env_file_encoding="utf-8")`; los *defaults* se validan por defecto | `infra/settings.py` | Sí |
| pydantic `ConfigDict(frozen=True)`, `@field_validator(..., mode="after")`, `@model_validator(mode="after")` | Modelos de dominio inmutables y validación cruzada | Sí |
| Typer `typer.Typer()`, `@app.command()`, `Annotated[..., typer.Argument()]`, `typer.Option(exists=True, dir_okay=False, readable=True)`, `typer.confirm(...)`, `raise typer.Exit(code=n)`, `typer.testing.CliRunner` | CLI, confirmación del operador, códigos de salida, pruebas de CLI | Sí |
| openpyxl `Workbook()`, `wb.active`, `ws.append(row)`, `wb.save(path)`; `load_workbook(filename, read_only=True)` + `wb.close()`; `iter_rows(min_row=..., values_only=True)`; `load_workbook(data_only=True)` | Lector y exportador Excel | Sí |
| `stdnum.co.nit`: `compact(number)` (quita `.`, `,`, `-`, espacios); `calc_check_digit(number_sin_dv) -> str` (pesos 3,7,13,…,71 de derecha a izquierda, `'01987654321'[s]`); `validate(number_con_dv)` lanza `InvalidLength` (fuera de 8–16 incluyendo DV), `InvalidFormat`, `InvalidChecksum`; `is_valid(...)`; `format(...)` → `213.123.432-1` | `validate` y `is_valid` esperan el **número con DV**; para validar un DV recibido aparte se compara `calc_check_digit(base) == dv` | Sí (código fuente) |
| PyYAML `yaml.safe_load(stream)` (nunca `yaml.load` sin `Loader`) | Carga de `selectors.yaml` | Sí |
| Typer `typer.Typer(pretty_exceptions_show_locals=False)`; la documentación indica que mostrar variables locales está desactivado por defecto para no exponer datos sensibles, y se fija explícitamente igual | Evitar que un traceback muestre el id o resultados (observación de seguridad 3) | Sí (tutorial "exceptions") |
| openpyxl: "By default openpyxl does not guard against quadratic blowup or billion laughs xml attacks. To guard against these attacks install defusedxml"; `openpyxl.xml.DEFUSEDXML` se activa si el paquete está instalado y `OPENPYXL_DEFUSEDXML` no es `"False"` | Prueba en T-36: `openpyxl.DEFUSEDXML is True` | Sí (index "Security", módulo `openpyxl.xml`) |

**Pendiente de verificación en T-46** (no confirmado por Context7): si openpyxl interpreta como
fórmula una cadena que empieza por `=`. El exportador debe neutralizar valores que empiecen por
`=`, `+`, `-`, `@`, tabulador o retorno de carro (inyección de fórmulas), escribir `identificacion`
como texto, y la prueba debe demostrarlo (T-46, T-47).

## Consecuencias

- (+) El modo base C + F funciona hoy, sin navegador, y lo pueden instalar operadores sin Chromium.
- (+) Todo el ciclo (código, pruebas, CI) lo automatizan los agentes; las pruebas nunca tocan el portal.
- (+) Habilitar E cuando se cumplan (a)–(d) es configuración + selectores reales, no reescritura.
- (−) Se mantiene código (adaptador E) que hoy no se usa en producción: se acota a lo necesario y
  sus partes dependientes del DOM real quedan BLOQUEADAS por T-14 (ver `specs/tareas.md`).
- (−) Con E habilitado, Python + Chromium en el equipo del operador (mitigable con `uv` y guía T-60).
- (−) El modo asistido limita el volumen si hay desafío en cada consulta (R-02).

## Estado

ACEPTADO (modificado respecto a la propuesta; ratificado por el usuario en el gate de Fase 3 (2026-10-09)). Auditoría de
dependencias con `pip-audit` en CI cuando exista `uv.lock` (T-31). La condición original de aceptación ("existe canal
web utilizable") **no se cumple hoy**; por eso la decisión se reformula: núcleo sin navegador + E
opcional y deshabilitado. Si la PQRSD revela un canal oficial documentado (B), se añade un adaptador
HTTP **autorizado** detrás del mismo puerto mediante un nuevo ADR.
