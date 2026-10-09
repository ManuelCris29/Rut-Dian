# Backlog de tareas

Estados: `TODO` · `EN_CURSO` · `BLOQUEADA` · `HECHA` · `DESCARTADA`
Una tarea de Fase N no inicia hasta que la Fase N-1 esté cerrada en `docs/ESTADO.md`.

## Fase 1 — Requisitos (agente: analista-requisitos)

| ID | Tarea | Entregable | Estado |
|---|---|---|---|
| T-01 | Presentar preguntas de `specs/requisitos.md` al humano y registrar respuestas | requisitos.md actualizado | TODO |
| T-02 | Definir campos de salida y finalidad del tratamiento | SPEC §5 confirmado | TODO |
| T-03 | Medir/registrar línea base del proceso manual (o supuesto aprobado) | tabla de indicadores | TODO |
| T-04 | Priorizar RF con MoSCoW y aprobar alcance MVP | SPEC §4 aprobado | TODO |

## Fase 2 — Viabilidad (agente: investigador-dian)

| ID | Tarea | Entregable | Estado |
|---|---|---|---|
| T-10 | Verificar estado de la URL original (fecha/hora, captura sin datos) | docs/investigacion/01-estado-url.md | TODO |
| T-11 | Inventario de canales oficiales DIAN (consulta estado, copia RUT, servicios para terceros, API/interoperabilidad, soporte) | 02-canales-oficiales.md | TODO |
| T-12 | Condiciones de uso, protección de datos y restricciones a la automatización | 03-condiciones-uso.md | TODO |
| T-13 | Evidencia de cómo lo resuelven empresas y proveedores (con fuentes) | 04-practicas-mercado.md | TODO |
| T-14 | Análisis técnico del canal elegible: formulario, desafíos de seguridad, sesión, tiempos (exploración manual asistida, ≤ 5 consultas con números del propio equipo autorizados) | 05-analisis-tecnico.md + snapshot sanitizado | TODO |
| T-15 | Tabla comparativa A–F y recomendación | docs/investigacion/INFORME-VIABILIDAD.md | TODO |
| T-16 | Redactar consulta formal a la DIAN (PQRSD) sobre canal autorizado para terceros | 06-borrador-pqrsd.md | TODO |

## Fase 3 — Diseño (agente: arquitecto)

| ID | Tarea | Entregable | Estado |
|---|---|---|---|
| T-20 | Confirmar o reemplazar ADR-0001 (stack) según informe de viabilidad | adr/0001 Aceptado | TODO |
| T-21 | ADR-0002 Puerto `RutSourcePort` y adaptadores | adr/0002 | TODO |
| T-22 | ADR-0003 Modo asistido ante desafíos de seguridad | adr/0003 | TODO |
| T-23 | Diagrama de arquitectura (C4 nivel 2) y flujo de secuencia | docs/ARQUITECTURA.md | TODO |
| T-24 | Desglosar tareas de Fase 4 con criterios de prueba | este archivo | TODO |

## Fase 4 — Desarrollo (agentes: desarrollador-python, ingeniero-rpa) — borrador, lo refina T-24

| ID | Tarea | Agente | Estado |
|---|---|---|---|
| T-30 | Esqueleto: `pyproject.toml` (uv), ruff, mypy, pytest, estructura `src/rut_checker` | desarrollador-python | TODO |
| T-31 | CI GitHub Actions: lint + mypy + tests offline en Ubuntu y Windows | ingeniero-devops | TODO |
| T-32 | `domain`: modelos, `QueryStatus`, validadores (normalización, DV con stdnum) | desarrollador-python | TODO |
| T-33 | `infra`: settings (pydantic-settings), logger JSON con enmascarado | desarrollador-python | TODO |
| T-34 | `ports.RutSourcePort` + `FakeSource` | desarrollador-python | TODO |
| T-35 | `application.BatchQueryService`: dedupe, ritmo, reintentos, parada por bloqueo | desarrollador-python | TODO |
| T-36 | `io`: lectores Excel/CSV, exportadores Excel/JSON/CSV | desarrollador-python | TODO |
| T-37 | `adapters.dian_portal`: page object + `selectors.yaml` desde snapshot real | ingeniero-rpa | TODO |
| T-38 | Detección de desafío de seguridad + pausa asistida | ingeniero-rpa | TODO |
| T-39 | `ContingencySource` | desarrollador-python | TODO |
| T-40 | CLI Typer: `consultar`, `lote`, `--formato`, `--salida` | desarrollador-python | TODO |

## Fase 5 — Pruebas (agente: ingeniero-pruebas)

| ID | Tarea | Estado |
|---|---|---|
| T-50 | Matriz de pruebas vs. criterios de aceptación y excepciones | TODO |
| T-51 | Fixtures HTML sanitizados: resultado, sin resultado, mantenimiento, desafío, estructura cambiada | TODO |
| T-52 | Pruebas de integración con fixtures (page.set_content / servidor local) | TODO |
| T-53 | Pruebas de seguridad: ids enmascarados, sin PII en logs/errores | TODO |
| T-54 | Prueba manual controlada en portal real (aprobación humana, ≤ 10 consultas) | TODO |
| T-55 | Informe de evidencias de laboratorio | TODO |

## Fase 6 — Producción (agente: ingeniero-devops)

| ID | Tarea | Estado |
|---|---|---|
| T-60 | Guía de instalación Windows, gestión de `.env` | TODO |
| T-61 | Plan de despliegue y reversión, versión etiquetada | TODO |
| T-62 | Monitoreo: reporte por ejecución y alerta por `ESTRUCTURA_CAMBIADA` | TODO |
| T-63 | Política de retención/eliminación de `output/` y `logs/` | TODO |
| T-64 | Manual de usuario y de administrador | TODO |
| T-65 | Informe final con métricas reales vs. línea base | TODO |
