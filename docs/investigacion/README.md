# Investigación (Fase 2)

Aquí el agente `investigador-dian` deja la evidencia. Cada archivo indica fecha/hora de consulta (America/Bogota) y fuentes.

| Archivo | Tarea |
|---|---|
| `01-estado-url.md` | T-10 |
| `02-canales-oficiales.md` | T-11 |
| `03-condiciones-uso.md` | T-12 |
| `04-practicas-mercado.md` | T-13 |
| `05-analisis-tecnico.md` (+ snapshot sanitizado) | T-14 |
| `06-borrador-pqrsd.md` | T-16 |
| `INFORME-VIABILIDAD.md` | T-15 |

## Punto de partida (búsqueda preliminar del 2026-10-09, por confirmar)
- Proveedores que automatizan el portal público y declaran depender de que la DIAN lo permita:
  [Kontalid](https://www.kontalid.com/consulta-estado-rut-dian-masiva/),
  [ConsultorContable — Verificador de RUT](https://www.consultorcontable.com/verificador-de-rut/),
  [Actualícese — Validador de terceros](https://actualicese.com/producto/aplicativo-para-consulta-masiva-de-terceros-en-la-dian-2026/).
- ConsultorContable reporta verificación Cloudflare/captcha y opción "Estado del RUT" intermitente o inhabilitada (comentarios fechados entre 2025-05 y 2026-09; detalle en `04-practicas-mercado.md`).
- Paquete PyPI `dian-person-rut-status` (MVP, sin repositorio ni licencia visibles) — no usar sin auditar.
- Desde el entorno de análisis, la URL original devolvió error de servidor el 2026-10-09.

## Resultado Fase 2 (2026-10-09)
- URL original: 302 → imagen oficial de mantenimiento "Consulta estado RUT… temporalmente fuera de operación" (14:20:55 COT). Ver `01-estado-url.md`.
- No se encontró API ni convenio accesible para privados (confirmación formal de la API pendiente vía PQRSD). Recomendación aceptada por el usuario el 2026-10-09: "C + F ahora, E condicionado"; B y D descartadas. Ver `INFORME-VIABILIDAD.md`.
