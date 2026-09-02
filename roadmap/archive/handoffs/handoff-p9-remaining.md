# Handoff Report — Phase 9 Execution (Tickets P9-04 … P9-08)

**Fecha:** 2026-09-01  
**De:** Principal Software Architect Agent  
**Para:** Próximo Agente de IA  
**Estado del Repositorio:** `main` en el commit `dd65368` (Clean working tree)

---

## 1. Estado Actual del Repositorio

- **Tickets Completados en P9:**
  - `P9-01` (README launch-ready): Mergeado a `main`.
  - `P9-02` (Documentation site & MkDocs Material): Mergeado a `main`.
  - `P9-03` (CI integration recipes & Composite Action): Mergeado a `main`.
- **Tickets Pendientes en P9:** `P9-04`, `P9-05`, `P9-06`, `P9-07`, `P9-08`.
- **Estado de Calidad:** `make verify` 100% verde (825 passed, 1 skipped, 0 failed; coverage 88.13% total, 95% core).
- **Invariante de Merge impuesta por el Human Owner:** 
  - El próximo agente **DEBE** ejecutar los tickets de P9 en sus respectivas ramas locales usando `make verify` como gate de calidad por ticket.
  - **NO hacer merge a `main` ni pedir OK intermedio por cada ticket**, sino acumular la ejecución y solicitar el approval gate de merge a `main` al finalizar **TODOS** los tickets de P9 (`P9-04` a `P9-08`).

---

## 2. Lecciones Aprendidas Recientes (P9-01 a P9-03)

1. **Lección 56 (MkDocs Strict Mode & Enlaces Externos)**: `mkdocs build --strict` trata cualquier archivo `.md` no incluido en `nav` o cualquier enlace relativo roto (como los que apuntan fuera de `docs/` a `roadmap/`) como error fatal. Todos los links a ADRs o specs fuera de `docs/` deben usar URLs absolutas de GitHub (`https://github.com/hbauzan/vhecfsck/blob/main/...`).
2. **Lección 57 (Sintaxis YAML en Nombres de Navegación con `#`)**: Los títulos en `mkdocs.yml` que contienen `#` (ej: `Qdrant #7147`) deben ir entre comillas dobles (`"Qdrant #7147"`) para evitar que el parser YAML interprete `#` como un comentario e ingrese una clave truncada.
3. **Lección 58 (Auto-formateado de Documentación Generada)**: Los scripts generadores de markdown (`generate_cli_docs.py`, `generate_schema_docs.py`, `generate_metrics_docs.py`) ejecutan `ruff format` sobre su salida. Si modificás o creás un generador, asegurate de formatear la salida con `ruff format` para no romper `test_lint_typing_config.py` durante `make verify`.
4. **Lección 59 (Entorno de Dependencias para `make verify`)**: `make verify` ejecuta tests de integración de LanceDB que requieren `pyarrow`. Si ejecutás `uv sync` para agregar grupos (como `--group docs`), siempre incluí `--extra lancedb` (`uv sync --group dev --group docs --extra lancedb`).

---

## 3. Guía de Ejecución Ticket por Ticket (P9-04 a P9-08)

### Ticket P9-04 — Anchor issues re-verification & Launch Post
- **Rama:** `feat/p9-04-anchor-verify-launch-post`
- **Contrato:**
  - Re-verificar contra versiones vigentes las 3 patologías históricas: Qdrant #7147, pgvector #244, Lance #4164.
  - Redactar `docs/launch-post.md` (o post de anuncio para Hacker News / Reddit / Twitter) con tono técnico denso, sin fluff de marketing, explicando la propuesta de valor: auditor de vectores 100% offline, read-only y empírico.
  - Ejecutar `make verify`.

### Ticket P9-05 — Release Engineering
- **Rama:** `feat/p9-05-release-engineering`
- **Contrato:**
  - Crear `.github/workflows/release.yml` para automatizar build de wheels con `hatchling` (con SPA estática embebida por `hatch_build.py`) y publicación a PyPI en tag push (`v0.1.0`).
  - Documentar el proceso de release en `docs/releasing.md`.
  - Asegurar que `CHANGELOG.md` tenga la versión `[0.1.0] - 2026-09-01` cerrada.
  - Ejecutar `make verify`.

### Ticket P9-06 — Pre-launch Review Pass
- **Rama:** `feat/p9-06-pre-launch-review`
- **Contrato:**
  - Auditoría hostil del repositorio completo: verificar 0 secrets comiteados, 0 links rotos, licencias 100% compatibles (MIT/Apache2), y demo en contenedor Docker funcionando sin red (`uvx vhecfsck demo`).
  - Actualizar `roadmap/backlog.md` y `CHANGELOG.md`.
  - Ejecutar `make verify`.

### Ticket P9-07 — Launch Execution
- **Rama:** `feat/p9-07-launch-execution`
- **Contrato:**
  - Preparar el anuncio de release y etiquetas de versión en Git.
  - Verificar que el tag `v0.1.0` esté listo para taggear.
  - Actualizar `roadmap/backlog.md` y `CHANGELOG.md`.
  - Ejecutar `make verify`.

### Ticket P9-08 — Post-launch Triage Window
- **Rama:** `feat/p9-08-post-launch-triage`
- **Contrato:**
  - Crear plantillas de GitHub Issues en `.github/ISSUE_TEMPLATE/` (`bug_report.md`, `feature_request.md`, `false_positive_report.md`).
  - Publicar FAQ final en `docs/faq.md`.
  - Marcar P9 completo en `roadmap/backlog.md`.
  - Ejecutar `make verify`.

---

## 4. Prompt Copiable para el Próximo Agente

Copiar y pegar el siguiente bloque para iniciar el nuevo agente:

```text
Usando dev-protocol, continuá la ejecución de la Fase 9 para llevar vhecfsck a v0.1.0.

Leé atentamente roadmap/handoff-p9-remaining.md, AGENTS.md, GEMINI.md y roadmap/lessons-learned.md.

Regla explícita impuesta por el Human Owner:
- Ejecutá todos los tickets pendientes de la Fase 9 (P9-04, P9-05, P9-06, P9-07, P9-08) secuencialmente en sus respectivas ramas locales.
- Por cada ticket, respetá TDD y el Hard Guardrail de ejecutar `make verify` antes de declarar el ticket listo.
- NO solicites aprobación humana intermedia ni intentes mergear a `main` por cada ticket individual.
- Acumulá el trabajo de P9 y ejecutá el gate de merge a `main` únicamente al terminar TODOS los tickets de P9 (al completar P9-08 con `make verify` verde).

Comenzá con P9-04 en la rama `feat/p9-04-anchor-verify-launch-post`.
```
