---
description: Implementa una tarea del backlog (Fase 4) con TDD, revisión y actualización de estado
argument-hint: <T-xx>
---

Implementa la tarea **$1** de `specs/tareas.md`.

1. Lee la tarea, su agente responsable y las dependencias. Si una dependencia no está `HECHA`, detente y dilo.
2. Marca la tarea `EN_CURSO`.
3. Delega en el agente responsable (`desarrollador-python`, `ingeniero-rpa` o `ingeniero-devops`) con este encargo:
   - Tarea: $1 (pega la fila completa y la sección relevante de `docs/ARQUITECTURA.md`).
   - Criterio de terminado: `specs/criterios-aceptacion.md` §Definición de terminado.
   - Recordatorio: consultar Context7 antes de usar APIs de librerías; TDD; nada contra el portal real.
4. Al volver, verifica tú mismo: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`. Si algo falla, devuélvelo al mismo agente con el error.
5. Delega en `revisor-codigo` la revisión del diff. Si el veredicto es `CAMBIOS REQUERIDOS`, vuelve al paso 3 con los hallazgos (máximo 2 iteraciones; luego pregúntame).
6. Haz commit con mensaje convencional: `feat(<modulo>): <resumen> ($1)`.
7. Marca `HECHA`, actualiza la bitácora de `docs/ESTADO.md` y dime en 3 líneas qué quedó.
