---
name: python-arquitectura
description: Arquitectura por capas y convenciones Python del proyecto (estructura src/rut_checker, puertos y adaptadores, modelos Pydantic, QueryStatus, configuración, logging, CLI Typer, pyproject con uv, ruff, mypy, pytest). Usar al crear o modificar cualquier módulo Python o al revisar código.
---

# Arquitectura y convenciones Python

## Estructura objetivo
```
pyproject.toml            # uv; [project.scripts] rut-checker = "rut_checker.cli:app"
config/selectors.yaml
src/rut_checker/
  domain/
    models.py             # IdentificationInput, RutResult, QueryOutcome (Pydantic, frozen)
    status.py             # class QueryStatus(StrEnum) — catálogo de specs/excepciones.md
    errors.py             # RutCheckerError y subclases (PortalUnavailable, SecurityChallengeDetected, StructureChanged, ...)
    validators.py         # normalize_identification(), validate_identification(), check_digit()
    masking.py            # mask_identification()
  ports/
    rut_source.py         # class RutSourcePort(Protocol): def query(self, ident: IdentificationInput) -> RutResult
  application/
    batch_service.py      # BatchQueryService: dedupe, ritmo, reintentos, parada, mapeo error->QueryStatus
    clock.py              # Clock/Sleeper inyectables (pruebas sin sleep real)
  adapters/
    dian_portal/          # ver skill playwright-rpa
    contingency_source.py
    fake_source.py
  io/
    readers.py            # read_identifications(path) Excel/CSV
    exporters.py          # export_excel / export_json / export_csv
  infra/
    settings.py           # pydantic-settings, prefijo RUT_
    logging.py            # logger JSON + filtro de enmascarado
  cli.py                  # Typer: consultar <id>, lote <archivo> --formato --salida
tests/
  unit/  integration/  e2e/  fixtures/html/  conftest.py
```

## Reglas de dependencia
`cli → application → ports ← adapters`; `domain` no depende de nadie (solo stdlib, pydantic y stdnum).
Inyección de dependencias manual en `cli.py` (función `build_service(settings)`); sin frameworks DI.

## Convenciones
- Python 3.12, `from __future__ import annotations` innecesario; usar tipos nativos (`list[str]`, `X | None`).
- Identificadores en inglés; docstrings Google-style en español.
- Modelos de dominio inmutables (`model_config = ConfigDict(frozen=True)`).
- Errores: jerarquía propia; el servicio traduce cada excepción a un `QueryStatus` en un único lugar.
- Sin estado global; settings se pasan explícitamente.
- Funciones ≤ 40 líneas; módulos ≤ 300 líneas.

## pyproject (claves)
```toml
[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E","F","W","I","B","UP","SIM","RUF","S","PT","N"]
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]
[tool.mypy]
strict = true
packages = ["rut_checker"]
[tool.pytest.ini_options]
addopts = "-m 'not portal_real' -q"
markers = ["portal_real: requiere el portal real de la DIAN; solo manual con aprobación"]
testpaths = ["tests"]
```

## Variables de entorno (prefijo `RUT_`)
`RUT_PORTAL_URL`, `RUT_HEADLESS=false`, `RUT_NAVIGATION_TIMEOUT_S=30`, `RUT_MIN_DELAY_BETWEEN_QUERIES_S=5`,
`RUT_MAX_RETRIES=2`, `RUT_HUMAN_CHALLENGE_TIMEOUT_S=120`, `RUT_OUTPUT_DIR=output`, `RUT_LOG_DIR=logs`, `RUT_SOURCE=dian_portal|contingency|fake`.
