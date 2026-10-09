---
description: Arranca o retoma el proyecto - verifica entorno y MCP, lee el estado y ejecuta la fase actual con sus agentes
allowed-tools: Read, Grep, Glob, Bash(python --version:*), Bash(python3 --version:*), Bash(uv --version:*), Bash(node --version:*), Bash(git status:*), Bash(git init:*), Bash(git add:*), Bash(git commit:*)
---

Actúas como **orquestador** del proyecto (ver @CLAUDE.md §2). No escribas código de producción tú mismo.

Estado actual del proyecto:
@docs/ESTADO.md

Entorno detectado:
- Python: !`python --version 2>&1 || python3 --version 2>&1`
- uv: !`uv --version 2>&1`
- Node (para MCP): !`node --version 2>&1`
- Git: !`git status --short 2>&1 | head -20`

Pasos:
1. Reporta en una tabla qué prerrequisitos faltan (uv, Python 3.12, Node ≥ 18, git) y cómo instalarlos en Windows. Si falta algo crítico para la fase actual, detente.
2. Si no existe repositorio git, inicialízalo y haz el primer commit del andamiaje (sin `data/`, `output/`, `logs/`, `.env`).
3. Comprueba que los servidores MCP `context7` y `playwright` respondan (una llamada mínima a cada uno). Si no, indica `claude mcp list` y cómo arreglarlo.
4. Resume en 5 líneas: fase actual, tareas abiertas de esa fase (de `specs/tareas.md`), bloqueos y supuestos.
5. Ejecuta la fase actual siguiendo `/fase <n>` (lee `.claude/commands/fase.md`), delegando en los agentes correspondientes.
6. Al terminar la ronda, actualiza `docs/ESTADO.md` y presenta: hecho / pendiente / preguntas para mí.
