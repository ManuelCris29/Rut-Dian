---
description: Evalúa el gate de la fase actual con evidencia y solicita aprobación humana para avanzar
allowed-tools: Bash(grep:*), Bash(uv run pytest:*), Bash(uv run ruff:*), Bash(uv run mypy:*)
---

Fase actual según `docs/ESTADO.md`:
!`grep -m2 -E "Fase actual|Estado de la fase" docs/ESTADO.md`

1. Toma el checklist de la fase en el skill `metodologia-fases`.
2. Para cada ítem, busca la evidencia concreta (archivo, sección, salida de comando). Si la fase es 4 o 5, ejecuta tú: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` y pega la salida.
3. Presenta una tabla: ítem | cumple (Sí/No) | evidencia.
4. Si algo no cumple: lista lo que falta y **no** cierres la fase.
5. Si todo cumple: pregúntame con AskUserQuestion si apruebo el cierre. Solo con mi "sí":
   - Marca la fase `APROBADA` con fecha y "aprobado por: usuario" en la tabla de gates.
   - Cambia "Fase actual" a la siguiente y su estado a `EN_CURSO`.
   - Commit: `docs(estado): cierre de fase N`.
