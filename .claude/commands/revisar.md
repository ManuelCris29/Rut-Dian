---
description: Lanza en paralelo la revisión de código y la de seguridad/privacidad sobre los cambios recientes
argument-hint: [rango git opcional, p. ej. main..HEAD]
allowed-tools: Bash(git diff:*), Bash(git log:*), Bash(git ls-files:*)
---

Cambios a revisar: !`git log --oneline -5 2>&1` y árbol de trabajo !`git diff --stat 2>&1`

Lanza **en paralelo** (dos llamadas a la herramienta Agent en el mismo mensaje):
- `revisor-codigo` sobre el rango `$ARGUMENTS` (por defecto los últimos 3 commits y el árbol de trabajo).
- `revisor-seguridad` sobre el mismo rango, más `git ls-files` completo.

Consolida ambos reportes en una sola tabla ordenada por severidad. Registra los bloqueantes como tareas nuevas en `specs/tareas.md` (ID `T-9x`) asignadas al agente correspondiente, y dime si recomiendas corregirlos ya.
