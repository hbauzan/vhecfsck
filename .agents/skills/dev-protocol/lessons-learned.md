# LESSONS LEARNED & ARCHITECTURAL INVARIANTS

**Este archivo es la memoria de handoff entre agentes.** Registra lo que una IA aprendió y que la siguiente necesita saber sin haber estado ahí: invariantes de arquitectura, patrones de rendimiento y decisiones que ya se probaron y no hay que volver a probar. Sobrevive a la sesión, a la compactación de contexto y al cambio de modelo — es lo único del proyecto que lo hace.

De ahí salen sus dos reglas, que están en el §5 del final y son las mismas que en [SKILL.md](./SKILL.md): se **lee** cuando entrás en frío o cuando una decisión concreta depende de una invariante, y se **escribe** cuando el usuario pide un handoff. Ninguna de las dos por reflejo.

---

## 0. Estado

**P0 Foundation completo** (P0-01…P0-15 `done`).
**P1 parcial en `main`:** P1-01…P1-04 `done` (models, IndexAdapter protocol, synthetic generator, pathologies).
**Próximo critical path:** **P1-05** (`SyntheticAdapter` — IVF + tombstone post-filter; ADR-0014) → P1-06 / P1-07 / P1-08.
**HEAD de referencia al handoff:** `68a4d55` merge P1-04 (`make verify` verde).
**Remote:** `origin` → `https://github.com/hbauzan/vhecfsck` (**PRIVATE**).
**Licencia / atribución:** Apache-2.0; credit = **hbauzan** (no “vhecfsck contributors”).
**Gate único:** `make verify` (lint + format-check + typecheck + test + coverage + layers + readonly).
**CI:** `.github/workflows/ci.yml` + `nightly.yml`. Sync en CI = `uv sync --group dev` (**nunca** `--all-extras`).

Residual dueño (no lo “arregles” vos solo):
- PyPI `vhecfsck` sigue libre (`404`); falta publicar placeholder con Trusted Publishing / token.
- Visibilidad del repo: sigue private hasta OK explícito.
- ADR-0012: la expansión de la `H` en copy público sigue abierta (no inventar gloss).

Las lecciones de `vhectorlab` **no** se copian: producto = auditor CLI offline, no stack web/daemon.

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

**Solution:** Probe the real artifact (`Makefile`, `vhecfsck <cmd> --help`). If absent, print the Thursday line and exit `3`. Gate failure / sync failure → `2`. Unknown verb → `4`. Taxonomy matches code-design exit codes. After P0-04, `./setup.sh verify` runs the real gate.

**Invariant:** Never fake a green health or a successful run for a feature that is not built yet.

## 4. Do not prepend Homebrew/`~/.local` over an explicit `PATH`

**Problem:** Prepending `/opt/homebrew/bin` to `PATH` shadow-hijacked a test-injected fake `uv` (and would hijack a contributor-pinned version).

**Solution:** Prefer `uv` already on `PATH`. Only append known install locations when `uv` is still missing.

**Invariant:** Tool discovery must not reorder an intentional `PATH`.

## 5. Never `uv sync --all-extras` (setup.sh, CI, or “convenience”)

**Problem:** `--all-extras` would pull every engine SDK and break the lean-base / `uvx vhecfsck demo` constraint (ADR-0002). Template CI often copies `--all-extras`.

**Solution:** `setup.sh` and GitHub Actions use plain `uv sync` / `uv sync --group dev`. Engine extras opt-in per adapter ticket.

**Invariant:** Default sync stays base (+ declared dependency groups). No `--all-extras` in setup or CI.

## 6. vhectorlab assets map to tickets, not to setup

**Problem:** Architect suggestions bundled Three.js / HUD / `.npz` / HF deploy into "reuse for setup".

**Solution:** Three.js + HUD colour semantics belong in P4/P6. Tensor/float32 corpus handling belongs in core/adapters. HF Spaces stays out of scope (no hosted SaaS).

**Invariant:** Do not grow `setup.sh` to host visualizer or deploy concerns. Follow the phase tickets.

## 7. Ruff has no path `lint.overrides` — scope ANN+D with per-file-ignores

**Problem:** Ticket P0-02 asks for ANN+D only on `core/` and `models/`. Current ruff rejects `[[tool.ruff.lint.overrides]]`.

**Solution:** Put `ANN` and `D` in global `lint.select`; suppress them via `per-file-ignores` on `tests/**`, package root modules (`cli`, `config`, `errors`, `logging`, …), `adapters/**`, `report/**`, `server/**`, and `scripts/**`. Extend-exclude `.agents`, `.claude`, `.cursor`, and `roadmap`.

**Invariant:** Do not reintroduce nonexistent ruff override tables. Keep product trees clean; do not “fix” roadmap prose or skill templates to satisfy format-check.

## 8. `make verify` is the only gate — do not invent a parallel one

**Problem:** Agents invent ad-hoc verify command lists or skip steps.

**Solution:** P0-04 owns `Makefile` / `make verify` = lint + format-check + typecheck + test + coverage (80 overall / 90 `core/`) + `layers` (import-linter) + `readonly` (AST guard). `verify-full` adds slow marks + mutation stub.

**Invariant:** Leave every ticket with `make verify` green. No shadow gate. No “green except …”.

## 9. Copyright credit is `hbauzan`; GitHub stays private; PyPI claim is owner-gated

**Problem:** Attribution, visibility, and PyPI publish were clarified after first passes.

**Solution:** `LICENSE` / `NOTICE` / authors = **hbauzan**. Repo PRIVATE until explicit OK. P0-13 filled `project.urls` and recorded in ADR-0012 that PyPI `0.0.0` publish needs a token / Trusted Publishing (not present in agent env).

**Invariant:** Attribution = `hbauzan`. Visibility and PyPI publish are owner-gated. Do not invent the `H` expansion in ADR-0012.

## 10. One ticket = one branch = one commit; never parallelize overlapping trees

**Problem:** Launching a background agent on P0-11 while the parent worked P0-07 caused a mixed commit on the wrong branch and a failed merge (“Already up to date”).

**Solution:** Serialise tickets that share `CHANGELOG` / `backlog` / `main`. Parallel only when filesets are disjoint **and** each agent owns a dedicated branch from a known `main` SHA.

**Invariant:** No concurrent writers on the same branch or on shared paperwork files.

## 11. Never merge a red gate; clean probe leftovers before commit

**Problem:** AST/typing probes (`_p0_02_*`, `_p0_08_*`, `_p0_09_*`) left on disk, or a failing suite, got merged when the agent raced ahead.

**Solution:** Probes live only inside a test’s `try/finally`. `make verify` must be green **before** `git commit`. If you discover main is red, fix on a `fix/…` branch immediately — do not start the next feature on a red base.

**Invariant:** No probe files in the tree at commit time. No knowingly-red merges to `main`.

## 12. Read-only SQL guard matches statement shapes, not prose

**Problem:** Substring `DELETE ` matched `client.delete on …` and docstring “mention delete without…”, failing the suite and briefly landing red on main.

**Solution:** `scripts/check_readonly.py` uses statement-shaped regex (`DELETE FROM`, `DROP TABLE`, `INSERT INTO`, `UPDATE … SET`, `ALTER TABLE`, `VACUUM`/`REINDEX`/`TRUNCATE`) with `(?<![.\w])`. Attribute calls and aliases still caught via AST.

**Invariant:** Do not loosen the denylist of write attrs. Do not return to naive substring SQL matching.

## 13. `vhecfsck/logging.py` is intentional — suppress A005, do not rename

**Problem:** Ruff `A005` flags shadowing stdlib `logging`.

**Solution:** Ticket P0-06 names the module `logging.py`. Keep the name; `per-file-ignores` includes `A005` for that file. Redaction has **no disable flag**.

**Invariant:** Do not rename to “avoid the lint”. Do not add a redaction bypass.

## 14. Coverage floor tests must track the growing package

**Problem:** `tests/unit/test_harness_config.py` subprocess coverage ran only `test_package` + `test_cli_stub`; after `errors.py` / `config.py` landed, overall coverage dipped under 80% inside that meta-test.

**Solution:** Keep `_COVERAGE_TARGETS` updated when new high-line-count modules ship, or measure coverage only via `make verify`’s coverage recipe and stop duplicating a brittle subset. Prefer extending targets over lowering `fail_under`.

**Invariant:** Never lower coverage floors to make a meta-test pass. Never weaken product tests.

## 15. Layering contracts need real packages; `models` stays a leaf

**Problem:** import-linter fails if contracted modules do not exist.

**Solution:** P0-08 added empty `vhecfsck/report/` and `vhecfsck/server/` scaffolds. Contracts: models imports nothing internal; core ⊬ adapters/server/cli/report; adapters ⊬ core; report ⊬ core/adapters.

**Invariant:** Metric logic stays in `core/`. Domain types in `models/` import no internal package modules. New packages must extend `.importlinter` in the same ticket that introduces them.

## 16. `AGENTS.md` is the playbook distill — hand-maintained

**Problem:** Skill template assumed `sync_agents_md.py --check` ownership; P0-12 requires a short playbook distill (<~80 lines) with “never write to an audited target”, etc.

**Solution:** Root `AGENTS.md` is hand-written from `roadmap/agent-playbook.md`. Do not regenerate it from the skill in a way that drops those guardrails. Pre-commit deliberately omits agents-md-sync.

**Invariant:** Keep `AGENTS.md` short, linked to playbook + metrics spec, with the hard guardrails verbatim in spirit.

## 17. Adapter / models prose must not trip the SQL readonly guard

**Problem:** Docstrings saying “vacuum” / “reindex” failed `scripts/check_readonly.py` because the guard matches statement-shaped `VACUUM\b` / `REINDEX\b` in string literals too.

**Solution:** Protocol and adapter module docs use synonyms (`rebuild`, `maintenance`, `remove`). Do not loosen the guard.

**Invariant:** Read-only prose in `adapters/` and `core/` must avoid denied SQL keyword tokens as whole words.

## 18. `TargetDescriptor.location` is pre-redacted; models stay a leaf

**Problem:** P0-06 requires redaction on descriptor locations, but import-linter forbids `models` → `logging`.

**Solution:** Callers pass `redact_secrets(raw)` into `TargetDescriptor.location`. No redaction import inside `models/`. Domain types are frozen dataclasses (no pydantic in base — ADR-0002 / P3-01).

**Invariant:** Redact at the boundary that builds the descriptor. Do not pull `logging` or pydantic into `models/` without an ADR.

## 19. Coverage + numpy: avoid reduction asserts that re-enter `numpy/__init__`

**Problem:** Under `pytest-cov`, `np.array_equal` / `.all()` / `np.allclose` can re-enter lazy numpy imports and raise `ImportError: cannot load module more than once per process`.

**Solution:** Prefer `.tobytes()`, Python loops, or scalar floats in tests. In synthetic code, eager-import `default_rng` from `numpy.random` (not lazy `np.random`).

**Invariant:** Do not rely on numpy reduction helpers in coverage-sensitive asserts when a byte/scalar check suffices.

## 20. Never purge `numpy` from `sys.modules` in the parent pytest process

**Problem:** `test_importing_package_does_not_import_numpy` deleted numpy from `sys.modules` after conftest had loaded it; later tests then hit an unrecoverable C-extension reload error.

**Solution:** Run that isolation check in a **subprocess**. Parent suite keeps its loaded numpy.

**Invariant:** Module-purge import discipline tests belong in a fresh interpreter, not in-process.

## 21. Synthetic hub placement: cluster centroids, not empty midpoints

**Problem:** Hubs at geometric midpoints between clusters sat in empty L2 space and never entered top-10 of in-cluster probes.

**Solution:** `inject_hubs` places hubs at large-cluster centroids (light inter-cluster blend). Brute-force hub tests use tight/small clusters or probes from the hub’s home cluster.

**Invariant:** Pathology operators must induce the claimed geometry; tests verify by brute force, not by trusting placement labels.

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
