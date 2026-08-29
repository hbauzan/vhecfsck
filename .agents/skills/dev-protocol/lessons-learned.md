# LESSONS LEARNED & ARCHITECTURAL INVARIANTS

**Este archivo es la memoria de handoff entre agentes.** Registra lo que una IA aprendió y que la siguiente necesita saber sin haber estado ahí: invariantes de arquitectura, patrones de rendimiento y decisiones que ya se probaron y no hay que volver a probar. Sobrevive a la sesión, a la compactación de contexto y al cambio de modelo — es lo único del proyecto que lo hace.

De ahí salen sus dos reglas, que están en el §5 del final y son las mismas que en [SKILL.md](./SKILL.md): se **lee** cuando entrás en frío o cuando una decisión concreta depende de una invariante, y se **escribe** cuando el usuario pide un handoff. Ninguna de las dos por reflejo.

---

## 0. Estado

Invariantes de la sesión P0-01 + P0-15. Las lecciones de `vhectorlab` **no** se copian: este producto es un auditor CLI offline, no un stack web con daemon.

---

## 1. `setup.sh` is a contributor console, not the product

**Problem:** A port of `vhectorlab/setup.sh` assumed two long-lived services (`uvicorn` + Vite), pid files, log dirs, port killing, and Hugging Face Spaces publish. That contradicts `vhecfsck` scope (no daemon, no SaaS, CLI-first, `uvx vhecfsck` is the hero).

**Solution:** Root `setup.sh` is a macOS contributor panel only. It runs `uv sync`, and when they exist, `make verify` / `vhecfsck demo` / `vhecfsck serve` in the **foreground**. No `nohup`, no `.pids/`, no `logs/`, no Vite `:5173`, no HF Spaces. Linux is deferred to `P9-09` after a real publish-readiness test.

**Invariant:** Never turn `setup.sh` into a process supervisor. When `demo` (P3-05) or `serve` (P4-06) land, wire them as foreground CLI calls — do not add background lifecycle.

## 2. Menu hierarchy: technical action primary, Hitchhiker secondary

**Problem:** Putting Guide quotes as the bold menu title made the panel hard to scan; operators need the real command first.

**Solution:** Each row is `[n] <bold white technical action>  (dim grey Hitchhiker quote)`. Banner stays `DON'T PANIC — Vector Index`. Exit primary text is `Exit the panel`; quote remains `So long, and thanks for all the fish`.

**Invariant:** Never let a Hitchhiker quote replace or outrank the technical action in the menu. Quotes stay in the dim parenthetical slot.

## 3. Missing capability is `INCONCLUSIVE` (exit 3), never fake-healthy

**Problem:** A menu that pretends `make verify` / `demo` / `serve` work before those tickets exist teaches false confidence and breaks CI later.

**Solution:** Probe the real artifact (`Makefile`, `vhecfsck <cmd> --help`). If absent, print the Thursday line and exit `3`. Gate failure / sync failure → `2`. Unknown verb → `4`. Taxonomy matches code-design exit codes.

**Invariant:** Never fake a green health or a successful run for a feature that is not built yet.

## 4. Do not prepend Homebrew/`~/.local` over an explicit `PATH`

**Problem:** Prepending `/opt/homebrew/bin` to `PATH` shadow-hijacked a test-injected fake `uv` (and would hijack a contributor-pinned version).

**Solution:** Prefer `uv` already on `PATH`. Only append known install locations when `uv` is still missing.

**Invariant:** Tool discovery must not reorder an intentional `PATH`.

## 5. Never `uv sync --all-extras` from the contributor console

**Problem:** `--all-extras` would pull every engine SDK and break the lean-base / `uvx vhecfsck demo` constraint (ADR-0002).

**Solution:** `setup.sh` runs plain `uv sync`. Engine extras are opt-in when an adapter ticket needs them.

**Invariant:** Default sync stays base (+ declared dependency groups). No `--all-extras` in `setup.sh`.

## 6. vhectorlab assets map to tickets, not to setup

**Problem:** Architect suggestions bundled Three.js / HUD / `.npz` / HF deploy into "reuse for setup".

**Solution:** Three.js + HUD colour semantics belong in P4/P6. Tensor/float32 corpus handling belongs in core/adapters. HF Spaces stays out of scope (no hosted SaaS).

**Invariant:** Do not grow `setup.sh` to host visualizer or deploy concerns. Follow the phase tickets.

---

## 5. Protocolo de Mantenimiento de Lecciones Aprendidas

Este archivo es caro de leer y fácil de arruinar. Si se lee por reflejo, se paga en cada sesión; si se escribe por reflejo, se llena de ruido y deja de servir para lo único que sirve: que la próxima IA arranque donde terminó la anterior.

### 5.1. Cuándo se LEE
El agente **DEBE** leerlo en estos tres casos, y no por defecto en el resto:
1. **Entrás en frío.** Sesión nueva sobre trabajo que no hiciste vos, retomada después de un handoff, o continuación después de compactar contexto. Es literalmente para lo que existe.
2. **Vas a diseñar algo nuevo.** Feature, módulo o build desde cero: leelo antes de decidir la forma, no después.
3. **Estás en la Fase 3 de un debug** ([debugging.md](./debugging.md)). Buena parte de los bugs son invariantes re-rotas; si una cubre el área, es una hipótesis que ya viene con evidencia y con fix conocido.

No hace falta para reviews, commits, sync de docs ni ediciones triviales.

### 5.2. Cuándo se ESCRIBE
**Solo cuando el usuario lo pide** — típicamente al preparar un handoff. Si descubriste una invariante durable, **proponéla en el reporte de entrega** y dejá que el usuario decida si entra. El criterio de admisión es alto: una invariante que un agente futuro no debe re-romper, en pocas líneas. Las tablas de mediciones y los hilos abiertos van a `current-research/` (si el repo lo usa), no acá.

### 5.3. Cuándo una lección ya no alcanza
Si un bug reincide sobre una invariante **que ya estaba escrita acá**, el problema no es de documentación: la prosa no enforcea nada. Esa invariante se ganó un guard estático o un test de regresión ([guardrails.md](./guardrails.md) §5). Anotarlo dos veces no la va a hacer cumplir.
