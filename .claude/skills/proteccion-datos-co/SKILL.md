---
name: proteccion-datos-co
description: Reglas de protección de datos personales para este proyecto (Ley 1581 de 2012, Decreto 1377 de 2013 compilado en el 1074 de 2015, reserva tributaria) - enmascarado de identificaciones, logs, fixtures ficticios, retención y qué nunca guardar. Usar al escribir código que toque identificaciones o resultados, al diseñar logs/exportaciones o al revisar seguridad.
---

# Protección de datos personales

> Las referencias normativas deben verificarse en fuentes oficiales (funcionpublica.gov.co, sic.gov.co, normograma.dian.gov.co) antes de citarlas en un informe. Este skill da reglas operativas, no asesoría legal.

## Principios aplicados (Ley 1581/2012)
- **Finalidad:** solo se consulta para la finalidad aprobada en `specs/requisitos.md`.
- **Necesidad/minimización:** solo los campos de SPEC §5.
- **Seguridad y confidencialidad:** acceso restringido a operadores autorizados.
- **Temporalidad:** retención definida; luego se elimina.

## Reglas de implementación
1. `mask_identification(value: str) -> str`: muestra solo los últimos 4 dígitos, el resto `*`. Si len ≤ 4 → todo `*`.
   `mask_identification("1234567890") == "******7890"`.
2. Logger estructurado (JSON) con campos permitidos: `run_id`, `row_index`, `id_masked`, `status`, `started_at`, `duration_ms`, `attempt`, `error_code`. **Nunca** el id completo, nombre o razón social.
3. Excepciones: mensajes sin id completo. Los `__str__`/`__repr__` de modelos con id deben enmascarar.
4. Archivos de salida con datos personales → solo en `output/` (en `.gitignore`), nombre sin ids: `resultado_<run_id>.xlsx`.
5. Snapshots/capturas de diagnóstico → solo en `logs/`, sanitizados (reemplazar dígitos de 6+ cifras y nombres por marcadores) y desactivados por defecto.
6. Fixtures de prueba: solo ids de la lista blanca ficticia (`tests/fixtures/README.md`), nombres "PERSONA FICTICIA UNO".
7. `.env` nunca se lee, imprime ni versiona; usar `.env.example`.

## Lista blanca ficticia sugerida para pruebas (solo FakeSource/fixtures, jamás contra el portal)
`1000000001`, `1000000002`, `1000000003`, `900000001` (con DV calculado en la prueba), `12A45` (inválido), `""` (vacío).

## Pruebas de seguridad mínimas
- Ejecutar un lote con FakeSource y comprobar que ni el log ni stderr contienen el id completo.
- Comprobar que una excepción con id no expone el id en `str(exc)`.
