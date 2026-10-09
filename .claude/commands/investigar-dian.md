---
description: Fase 2 - investiga canales oficiales de la DIAN para consultar el estado del RUT y produce el informe de viabilidad
argument-hint: [enfoque opcional, p. ej. "solo canales oficiales"]
---

Delega en el subagente `investigador-dian` las tareas T-10 a T-16 de `specs/tareas.md`.
Enfoque adicional del usuario (si lo hay): $ARGUMENTS

Contexto que debes pasarle:
- Pregunta central y estructura del informe: sección 12 de las instrucciones del proyecto (resumida en el propio agente).
- Hallazgos previos y su clasificación: `specs/SPEC.md` §3.
- Fecha de hoy y zona horaria America/Bogota para registrar las comprobaciones.

Cuando regrese:
1. Lanza `revisor-seguridad` sobre `docs/investigacion/`.
2. Muéstrame: resumen ejecutivo, tabla comparativa y recomendación, y las decisiones que necesitas de mí (usa AskUserQuestion).
3. Actualiza `docs/ESTADO.md` (decisiones, riesgos, pendientes). No cierres la fase sin mi aprobación.
