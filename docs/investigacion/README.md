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
- ConsultorContable reporta verificación Cloudflare/captcha y opción "Estado del RUT" intermitente (comentarios mayo–junio 2026).
- Paquete PyPI `dian-person-rut-status` (MVP, sin repositorio ni licencia visibles) — no usar sin auditar.
- Desde el entorno de análisis, la URL original devolvió error de servidor el 2026-10-09.
