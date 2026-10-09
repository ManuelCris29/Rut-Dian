# Criterios de aceptación (Gherkin)

```gherkin
Característica: Consulta del estado del RUT

  Escenario: Número válido con resultado
    Dado un número de identificación válido ficticio "900000001"
    Y una fuente que devuelve estado "ACTIVO"
    Cuando ejecuto la consulta individual
    Entonces el resultado tiene estado_consulta "EXITOSA"
    Y el log técnico contiene "*****0001" y no contiene "900000001"

  Escenario: Número inválido
    Dado el número "12A45"
    Cuando ejecuto la consulta
    Entonces el estado es "ENTRADA_INVALIDA"
    Y no se abre el navegador

  Escenario: Desafío de seguridad
    Dado que la fuente presenta un desafío de seguridad
    Cuando el operador no lo resuelve dentro del tiempo configurado
    Entonces el estado es "REQUIERE_INTERVENCION_HUMANA"
    Y el sistema no intenta resolverlo automáticamente

  Escenario: Cambio en la página
    Dado un HTML de resultado sin el selector obligatorio de estado
    Cuando se extrae el resultado
    Entonces el estado es "ESTRUCTURA_CAMBIADA"
    Y el lote se detiene

  Escenario: Portal en mantenimiento
    Dado que el canal responde con la página de mantenimiento
    Cuando ejecuto un lote de 3 números
    Entonces los 3 quedan en "PENDIENTE_VALIDACION_MANUAL" tras agotar reintentos
    Y el archivo de salida indica fuente y fecha de cada fila

  Escenario: Lote con duplicados
    Dado un archivo con "900000001" dos veces
    Cuando ejecuto el lote
    Entonces se realiza una sola consulta a la fuente
    Y ambas filas reciben el mismo resultado

  Escenario: Exportación
    Dado un lote procesado
    Cuando exporto a Excel
    Entonces el archivo contiene una fila por identificación de entrada
    Y las columnas definidas en SPEC §5, incluidas fuente y fecha de consulta

  Escenario: Lote mixto de cédulas y NIT
    Dado un archivo con la cédula ficticia "1000000001" y el NIT ficticio "900000001" con DV incorrecto
    Cuando ejecuto el lote
    Entonces la cédula se consulta
    Y el NIT queda en "ENTRADA_INVALIDA" sin consultar la fuente

  # Escenarios G9–G12 incorporados en Fase 3 (2026-10-09; decisiones D-1..D-5)

  Escenario: Copia del RUT vigente (G9)
    Dado la cédula ficticia "1000000001" con fecha_copia_rut de hace 30 días y responsable "USR-001"
    Y la fuente configurada "contingency"
    Cuando ejecuto el lote
    Entonces el estado es "VALIDADA_COPIA_RUT"
    Y la fuente es "COPIA_RUT_TERCERO"
    Y la observación incluye la fecha de la copia y el responsable
    Y estado_rut y nombre_o_razon_social quedan vacíos
    Y el log técnico no contiene "1000000001" ni la observación libre

  Escenario: Copia del RUT vencida (G10)
    Dado la cédula ficticia "1000000002" con fecha_copia_rut de hace 31 días y responsable "USR-001"
    Cuando ejecuto el lote
    Entonces el estado es "PENDIENTE_VALIDACION_MANUAL"
    Y la observación contiene "copia vencida"

  Escenario: Portal deshabilitado (G11)
    Dado RUT_SOURCE "dian_portal" y RUT_PORTAL_ENABLED "false"
    Cuando ejecuto el lote
    Entonces la CLI termina con código 2 y un mensaje que cita las condiciones (a)–(d)
    Y no se abre el navegador
    Y no se realiza ninguna petición de red

  Escenario: Ritmo responsable (G12)
    Dado una fuente que consulta un sistema externo y RUT_MIN_DELAY_BETWEEN_QUERIES_S "5"
    Cuando ejecuto un lote de 3 números válidos distintos
    Entonces entre consultas consecutivas transcurren al menos 5 s
    Y un valor de configuración menor a 3 s es rechazado al iniciar
```

> Los escenarios G3 y G4 solo se consideran cumplidos con fixtures **reales** sanitizados (T-48/T-51,
> bloqueados por T-14). Los fixtures sintéticos de `tests/fixtures/html/sintetico/` prueban el
> mecanismo, no el portal, y no se citan como evidencia del portal (D-4).

## Definición de terminado (por tarea)

- Prueba(s) escritas antes del código y en verde: `uv run pytest -m "not portal_real"`
- `uv run ruff check .` y `uv run ruff format --check .` sin errores; `uv run mypy src` sin errores
- Sin datos personales reales en código, fixtures, logs ni commits
- `specs/tareas.md` y `docs/ESTADO.md` actualizados
- Revisión de `revisor-codigo` sin hallazgos bloqueantes
