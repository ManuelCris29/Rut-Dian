# ADR-0001 — Stack tecnológico de automatización

- **Estado:** PROPUESTO (se acepta, modifica o descarta al cerrar la Fase 2)
- **Fecha:** 2026-10-09

## Contexto

Se sugirieron Power Automate Desktop, UiPath y Python con Playwright o Selenium.
Condiciones particulares de este proyecto:

1. El desarrollo lo ejecutan **agentes de Claude Code** desde terminal: necesitan crear, ejecutar y
   probar el código sin intervención en interfaces gráficas.
2. La fuente es incierta (portal en mantenimiento; posible canal oficial distinto) → se necesita poder
   cambiar de adaptador barato.
3. Hay un desafío de seguridad (captcha/Cloudflare) que **no se puede evadir** → el navegador debe ser
   visible y la automatización debe poder pausar y ceder control al operador.
4. Equipo con experiencia en UiPath y Power Automate (ventaja para mantenimiento) y en Python.

## Alternativas

| Criterio | Power Automate Desktop | UiPath | Python + Selenium | **Python + Playwright** | requests/httpx (HTTP directo) |
|---|---|---|---|---|---|
| ¿Lo pueden construir y probar agentes desde CLI? | No (flujos en editor gráfico) | Parcial (XAML, requiere Studio) | Sí | **Sí** | Sí |
| Pruebas automatizadas offline | Muy limitado | Test Suite (licencia) | Sí | **Sí, pytest-playwright + fixtures** | Sí |
| Esperas automáticas / estabilidad | Media | Alta | Manual (explicit waits) | **Alta (auto-wait, locators)** | N/A |
| Pausa asistida en navegador visible | Sí | Sí | Sí | **Sí (`page.pause()` / espera de selector)** | No: no hay navegador → descartado |
| Licenciamiento | Incluido en Windows; nube/desatendido con licencia | Comercial (Community limitada) | Libre | **Libre (Apache-2.0)** | Libre |
| Control de versiones / revisión de código | Pobre | Medio | Bueno | **Bueno** | Bueno |
| MCP para exploración por agentes | No | No | No | **Sí (Playwright MCP)** | No |
| Riesgo de cumplimiento | Bajo | Bajo | Bajo | Bajo | **Alto**: tienta a usar endpoints internos → descartado |

## Decisión propuesta

**Python 3.12 + Playwright (navegador visible, sin stealth)**, con la fuente aislada en un puerto
(`RutSourcePort`). Selenium se descarta por menor estabilidad sin aportar ventajas. HTTP directo se
descarta por cumplimiento. PAD/UiPath se descartan **para este proyecto construido por agentes**,
pero quedan como opción de implementación alternativa si la organización exige su plataforma RPA
corporativa: el diseño (estados, excepciones, selectores, specs) es transferible.

## Consecuencias

- (+) Todo el ciclo (código, pruebas, CI) es automatizable por los agentes.
- (+) Cambiar de fuente (portal → API oficial → proveedor) no toca dominio ni exportación.
- (−) Requiere Python + navegador en el equipo del operador (mitigable con instalador/uv).
- (−) El modo asistido limita el volumen si el desafío aparece en cada consulta (riesgo R-02).

## Condición de aceptación

Se acepta solo si `docs/investigacion/INFORME-VIABILIDAD.md` concluye que existe un canal oficial con
interfaz web utilizable sin evadir controles. Si la recomendación es API oficial o proveedor, Playwright
pasa a ser opcional y se reemplaza por un adaptador HTTP **documentado y autorizado**.
