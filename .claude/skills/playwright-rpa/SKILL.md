---
name: playwright-rpa
description: Patrones de Playwright para Python en este proyecto - page object del canal DIAN, selectores en YAML, detección de mantenimiento/desafío/cambio de estructura, pausa asistida, fixtures HTML offline y pruebas con pytest-playwright. Usar al implementar o probar el adaptador de navegador, o al actualizar selectores.
---

# Playwright RPA — patrones del proyecto

> Verifica siempre la API vigente con Context7 (`/microsoft/playwright-python`) antes de codificar. Los fragmentos siguientes son estructurales, no copiables a ciegas.

## Estructura
```
src/rut_checker/adapters/dian_portal/
  __init__.py
  source.py          # DianPortalSource(RutSourcePort)
  page.py            # DianQueryPage: page object (navegar, diligenciar, enviar, leer)
  detection.py       # is_maintenance(), has_security_challenge(), assert_structure()
  extractor.py       # HTML/locators -> RawRutResult (sin lógica de negocio)
  selectors.py       # carga y valida config/selectors.yaml con Pydantic
config/selectors.yaml
tests/fixtures/html/{resultado_ok,sin_resultado,mantenimiento,desafio,estructura_cambiada,incompleto}.html
```

## selectors.yaml (forma — los valores salen del snapshot real, NO inventar)
```yaml
version: "AAAA-MM-DD"          # fecha del snapshot de docs/investigacion
source_snapshot: docs/investigacion/05-analisis-tecnico.md
form:
  id_input:      { strategy: label, value: "<pendiente snapshot>" }
  submit_button: { strategy: role,  role: button, name: "<pendiente snapshot>" }
result:
  status:        { strategy: css,   value: "<pendiente snapshot>", required: true }
  name:          { strategy: css,   value: "<pendiente snapshot>", required: false }
  no_result_msg: { strategy: text,  value: "<pendiente snapshot>" }
detection:
  maintenance_markers: ["<texto real de la página de mantenimiento>"]
  challenge_markers:   ["<iframe/elemento real del desafío>"]
```

## Orden de detección tras cada navegación/envío
1. `is_maintenance(page)` → `PortalUnavailable`
2. `has_security_challenge(page)` → `SecurityChallengeDetected` (no tocar el widget)
3. Esperar formulario/resultado con timeout → `TimeoutError` → `TIEMPO_AGOTADO`
4. `assert_structure(page, required_selectors)` → `StructureChanged`

## Pausa asistida (concepto)
- El servicio de aplicación captura `SecurityChallengeDetected`, emite un aviso claro en la CLI ("Resuelva la verificación en la ventana del navegador; esperando hasta N s") y espera a que aparezca el formulario/resultado esperado con `timeout=HUMAN_CHALLENGE_TIMEOUT_S`.
- Si vence → `REQUIERE_INTERVENCION_HUMANA`. Nunca se hace clic programático sobre el desafío.

## Lanzamiento del navegador
- `headless` desde settings; por defecto `False` en ejecución real. En CI con fixtures puede ser `True`.
- Un `BrowserContext` por lote; página nueva ante `SESION_VENCIDA`.
- Sin `args` que oculten automatización, sin `user_agent` personalizado, sin proxy.
- Cerrar contexto/navegador en `finally` / context manager.

## Pruebas offline
- Fixture `page` de pytest-playwright + `page.set_content(Path(...).read_text())` para el extractor y la detección.
- Para flujos de navegación, servidor HTTP local (`http.server` en un hilo, fixture de sesión) que sirve `tests/fixtures/html/`, y `DianPortalSource(base_url=local_url)`.
- Marcar `@pytest.mark.portal_real` cualquier prueba que use la URL real; excluida por defecto en `pyproject.toml` (`addopts = "-m 'not portal_real'"`).

## Mantenimiento ante cambios del portal
1. `ESTRUCTURA_CAMBIADA` en producción → snapshot sanitizado en `logs/`.
2. `investigador-dian` documenta el nuevo DOM en `docs/investigacion/`.
3. `ingeniero-rpa` actualiza `selectors.yaml` + fixture + prueba; sube `version`.
