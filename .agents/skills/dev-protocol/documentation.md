# DOCUMENTATION SYNCHRONIZATION WORKFLOW

Update documentation **only when the change actually affects that asset**. Do not touch every file on every micro-fix — that wastes tokens and creates noise.

These documents are the recovery core of the codebase. Keep them accurate; do not keep them busy.

Names below are **defaults**. If the repo already has an equivalent, update **that** file — do not create the default name by reflex.

| File (or the repo's equivalent) | Update when… | Do **not** update when… |
| :--- | :--- | :--- |
| **`manifest.json`** | Version bumps, or `state_schema` / `constraints` change (new config field, default, range, or vector dim). | Pure refactors, bug fixes that leave the config contract unchanged. |
| **`CHANGELOG.md`** | Releases or **notable** capability changes (new provider, new surface, security posture change). Append a short section. | Every PR, typo fix, or internal cleanup. |
| **`architecture_spec.md`** *or* `roadmap/` + ADRs | Contracts change: API shapes, provider interface, data schemas, security/scalability policies, prompt/templating contracts, token/latency expectations. | Implementation details that stay within an existing contract. Do not invent `architecture_spec.md` if the repo already keeps contracts in `roadmap/` / `adr/`. |
| **`README.md`** | How to install, configure, or run the system changes (tooling, scripts, prerequisites). | Internal code changes that do not affect first-time setup. |
| **`CONTEXT.md`** *or* `roadmap/glossary.md` | Domain language changes (new term, renamed concept, retired alias). | Code-only changes that use existing terms. |
| **`current-research/`** (si el repo lo usa) | Descubrimientos empíricos que no entran en una lección de una línea (mediciones, estudios, “por qué X se comporta así”). | Bug fixes rutinarios: destilá la invariante en el lessons-learned del producto y linkeá acá la evidencia. |
| **Product `lessons-learned.md`** (default `roadmap/lessons-learned.md`; never inside the skill pack) | **Preparing a handoff**, or when the user explicitly asks. This file is the durable memory a fresh agent inherits, so the bar is an **invariant a future agent must not re-break** — short, and pointing at `current-research/` for the evidence when that folder exists. | Closing an ordinary task. Propose the lesson in your hand-off report and let the user decide: written by reflex, the file fills with noise and stops working as a handoff, which is the one job it has. Also: no measurement tables, no open science threads. See [lessons-learned.template.md](./lessons-learned.template.md) §5. |

### Manifest shape (slim)

`manifest.json` holds **current state only**:

- `project`, `version`
- `state_schema` (live config contract)
- `constraints` (domain limits the app actually enforces)

It is **not** a historical feature-flag ledger. Capability history lives in `CHANGELOG.md`.

### Agent handoff bundle (opcional)

Si el repo tiene un script de empaquetado de contexto para LLMs externos (p. ej. genera un `context.txt` gitignored), regeneralo cuando necesites un handoff fresco. No es asset versionado ni parte del doc-sync obligatorio.

---

## CONTEXT & BLUEPRINT WORKFLOW

By default, the codebase domain context is managed in a glossary format to ensure clean domain definitions. However, a specialized blueprint mode exists for tracking codebase layout.

### 1. CONTEXT.md (Standard Run - Default)
Behaves strictly as a **Domain Model Glossary & Ubiquitous Language** reference, devoid of code or implementation details.

- **Structure**: Define terms precisely under subheadings. Keep definitions tight (1-2 sentences max defining what a concept *is*, not what it *does*).
- **Aliases**: Be opinionated. If multiple words exist for the same concept, pick the canonical term and list the others under an `_Avoid_` section.
- **Relationships**: Show bold term names and express cardinality/relationships between concepts.
- **Context Mapping**: For repositories with multiple subdomains or modules, a `CONTEXT-MAP.md` at the root must map out each context (e.g. `[Ordering](./src/ordering/CONTEXT.md)`) and their relationships.
- **Update Frequency**: Update terms inline as decisions are made; do not batch glossary updates. Skip entirely if no domain terms changed.

### 2. CONTEXT.blueprint.md (Bootstrap Run)
The **Bootstrap Run** is a specialized mode containing a comprehensive codebase re-generation blueprint.

- **Activation**: Activated in one of two ways:
  1. Setting `"bootstrap_run": true` in `manifest.json`.
  2. Explicit declaration by the user in the prompt.
- **Output File**: Write/update the blueprint in a separate file: **`CONTEXT.blueprint.md`**.
- **Content Requirements**:
  - File-by-file inventory and mapping.
  - Complete structural dependencies between modules.
  - Technical debt analysis and context anchors.
  - Absolute context density to enable repository regeneration from zero.
