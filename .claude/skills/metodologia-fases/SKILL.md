---
name: metodologia-fases
description: Metodología por fases del proyecto de consulta del RUT (requisitos, viabilidad, diseño, desarrollo, pruebas, producción), entregables mínimos y criterios de gate de cada fase. Usar al planear, ejecutar o cerrar cualquier fase, o al actualizar docs/ESTADO.md.
---

# Metodología por fases y gates

Regla de oro: **no se avanza de fase sin pasar el gate y sin aprobación humana registrada** en `docs/ESTADO.md` (tabla "Gates de fase": estado `APROBADA`, quién, fecha).

## Gates

### Fase 1 — Requisitos
- [ ] AS-IS y TO-BE en Mermaid en `specs/requisitos.md`
- [ ] Actores, reglas RN-xx, volumen, frecuencia, destino definidos o como `[SUPUESTO]` aprobado
- [ ] Campos de salida y finalidad del tratamiento confirmados
- [ ] Criterios de aceptación en Gherkin
- [ ] Indicadores con método de medición de línea base
- [ ] Sin preguntas críticas abiertas (o supuesto aprobado por el humano)

### Fase 2 — Viabilidad
- [ ] `docs/investigacion/INFORME-VIABILIDAD.md` con las 11 secciones y la tabla comparativa
- [ ] Estado de la URL original verificado con fecha/hora
- [ ] Cada hallazgo clasificado Confirmado / Pendiente / Descartado con fuente y fecha
- [ ] Recomendación explícita y contingencia definida
- [ ] Revisión de `revisor-seguridad` sin bloqueantes
- [ ] El humano acepta la alternativa recomendada

### Fase 3 — Diseño
- [ ] ADR-0001 ACEPTADO (o reemplazado), ADR-0002, ADR-0003
- [ ] `docs/ARQUITECTURA.md` con C4-2, secuencia y estructura de paquetes
- [ ] Tareas de Fase 4 refinadas con pruebas asociadas
- [ ] Revisión de seguridad del diseño

### Fase 4 — Desarrollo
- [ ] Todas las tareas Must en `HECHA`
- [ ] `pytest -m "not portal_real"`, `ruff`, `mypy` en verde (salida pegada en ESTADO.md)
- [ ] CI en verde
- [ ] `revisor-codigo`: APROBADO o con observaciones menores

### Fase 5 — Pruebas
- [ ] Matriz de pruebas sin huecos en criterios/excepciones
- [ ] Cobertura ≥ 85 % en `domain` y `application`
- [ ] Informe de laboratorio con salidas reales
- [ ] Prueba manual controlada en portal real ejecutada por el humano (o justificada su omisión)
- [ ] Revisión de seguridad sin bloqueantes

### Fase 6 — Producción
- [ ] Instalación, despliegue/reversión, operación, retención documentados
- [ ] Manuales de usuario y administrador
- [ ] Validación del negocio + confirmación de cumplimiento registradas
- [ ] Informe final con métricas reales vs. línea base

## Formato de actualización de `docs/ESTADO.md`
- Cambiar "Fase actual" y "Estado de la fase".
- Añadir decisiones (fecha, decisión, referencia), supuestos, riesgos (prob/impacto/mitigación).
- Bitácora: `- AAAA-MM-DD — <qué se hizo> (<agente>)`.

## Clasificación de información
`[CONFIRMADO]` fuente verificable · `[PENDIENTE]` requiere confirmación · `[DESCARTADO]` con motivo · `[SUPUESTO]` provisional.
