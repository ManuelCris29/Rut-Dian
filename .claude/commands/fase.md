---
description: Ejecuta una fase del proyecto (1-6) delegando en los agentes responsables
argument-hint: <numero-de-fase 1-6>
---

Ejecuta la **Fase $1** como orquestador. Reglas: @CLAUDE.md §2 y skill `metodologia-fases`.

Primero valida en `docs/ESTADO.md` que la fase anterior a la $1 esté `APROBADA` (salvo Fase 1). Si no lo está, detente y dime qué falta.

Plan por fase (delegar con la herramienta Agent (antes llamada Task) al subagente indicado; en paralelo solo lo independiente):

- **Fase 1:** `analista-requisitos` → tareas T-01..T-04. Presenta sus preguntas al humano con AskUserQuestion (máx. 4 por ronda) y vuelve a delegarle las respuestas.
- **Fase 2:** `investigador-dian` → T-10..T-16. Luego `revisor-seguridad` sobre el informe. Presenta la recomendación y las decisiones al humano.
- **Fase 3:** `arquitecto` → T-20..T-24. Luego `revisor-seguridad` sobre el diseño.
- **Fase 4:** por cada tarea `TODO` en orden de dependencias, ejecuta el flujo de `/implementar <T-xx>`. Tras cada 2–3 tareas, `/revisar`. `ingeniero-devops` hace T-31 justo después de T-30.
- **Fase 5:** `ingeniero-pruebas` → T-50..T-55; bugs encontrados se asignan a `desarrollador-python` o `ingeniero-rpa`; luego `revisor-seguridad`.
- **Fase 6:** `ingeniero-devops` → T-60..T-63; `documentador` → T-64..T-65.

Durante la fase:
- Pasa a cada subagente: la tarea exacta, archivos de entrada y criterio de terminado. No le pidas que lance otros agentes.
- Si un subagente reporta `BLOQUEADA`, registra el bloqueo en `docs/ESTADO.md` y decide: reasignar, preguntar al humano o saltar a otra tarea independiente.
- Cuando todas las tareas de la fase estén `HECHA`, ejecuta `/cerrar-fase`.
