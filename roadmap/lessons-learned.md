# LESSONS LEARNED & ARCHITECTURAL INVARIANTS

**Este archivo es la memoria de handoff entre agentes de `vhecfsck`.** Vive en
`roadmap/`, no dentro del pack `dev-protocol`. Registra lo que una IA aprendió
y que la siguiente necesita saber sin haber estado ahí: invariantes de
arquitectura, patrones de rendimiento y decisiones que ya se probaron y no hay
que volver a probar. Sobrevive a la sesión, a la compactación de contexto y al
cambio de modelo — es lo único del proyecto que lo hace.

El pack solo trae el template y el protocolo de lectura/escritura:
[`.agents/skills/dev-protocol/lessons-learned.template.md`](../.agents/skills/dev-protocol/lessons-learned.template.md)
§5. Se **lee** cuando entrás en frío o cuando una decisión concreta depende de
una invariante, y se **escribe** cuando el usuario pide un handoff. Ninguna de
las dos por reflejo.

---

## 0. Estado

**P0 Foundation completo** (P0-01…P0-15 `done`).
**P1 completo** en `main` (P1-01…P1-08 `done`).
**P2 completo** en `main` (P2-01…P2-11 `done`).
**P3 completo** en `main` (P3-01…P3-09 `done`).
**P4 completo** en `main` (P4-01…P4-11 `done` — 3D projection, binary transport, FastAPI server, SPA visualizer; P4-11 hatch build hook in `hatch_build.py`, Node-free clean machine CI smoke residual P9-05).
**P5 completo** en `main` (P5-01…P5-10 `done` — LanceDB adapter).
**P6 completo** en `main` (P6-01…P6-09 — progressive LOD, live
progress, query probe, partition views, tombstone layer, camera tour, README GIF,
accessible palettes, visual regression).
**Playwright Visualizer E2E slice completo** en `main` (WebGL2, screenshot regression, WS resilience, probe interaction, axe accessibility, colour-by baselines).
**P7 completo** en `main` (P7-01…P7-08 `done` — container harness, Qdrant/Postgres adapters, qdrant#7147, pgvector#244, graph stats UNAVAILABLE, lance#4164, engine matrix & guides).
**P8-01 / P8-02 / P8-08 / P8-09 / P8-11** `done` en `main` (calibration harness, dimension-aware threshold profiles, fuzzing, error audit, security review).
**Próximo critical path:** **P8-03** (baseline y delta mode).
**HEAD de referencia al handoff:** `main` post P8-02 (commit `d8f03cb`).
**Remote:** `origin` → `https://github.com/hbauzan/vhecfsck` (**PRIVATE**).
**Licencia / atribución:** Apache-2.0; credit = **hbauzan** (no “vhecfsck contributors”).
**Gate único:** `make verify` (lint + format-check + typecheck + coverage + layers + readonly). `coverage` is the suite; `make test` is the inner loop.
**CI:** `.github/workflows/ci.yml` + `nightly.yml`. Sync en CI = `uv sync --group dev` (**nunca** `--all-extras`).

Stack en `main` (además de P0/P1):
- `vhecfsck/core/{ground_truth,canary,hubness,fragmentation,partitions,verdict,sampling}.py`
- `vhecfsck/pipeline.py` — `run_audit`
- `vhecfsck/models/report.py` — dataclasses precursoras (P3-01 las vuelve pydantic)
- `vhecfsck/synthetic/scenarios.py` — `size` ∈ `{tiny, small, large}`; `tiny` ≈ 80 vectores
- `tests/oracle/` + `tests/property/` (incl. determinism P2-11)
- `setup.sh` verbo `clean` / menú `[5]` — solo pytest de **este** checkout

Residual dueño (no lo “arregles” vos solo):
- PyPI `vhecfsck` sigue libre (`404`); falta publicar placeholder con Trusted Publishing / token.
- Visibilidad del repo: sigue private hasta OK explícito.
- ADR-0012: la expansión de la `H` en copy público sigue abierta (no inventar gloss).
- Wall/RSS budgets de `release-plan.md` §4: vacíos hasta **P8-04** — no inventar números.
- Plan de alcance MVP LanceDB en P3: ver commit `4d7582e` / roadmap — no ensanches P3-09 sin leerlo.

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

**Solution:** P0-04 owns `Makefile` / `make verify` = lint + format-check + typecheck + **coverage** (one instrumented pytest; 80 overall / 90 `core/`) + `layers` (import-linter) + `readonly` (AST guard). `make test` is the uninstrumented inner loop, not a verify prerequisite. `verify-full` adds slow marks + mutation stub.

**Invariant:** Leave every ticket with `make verify` green **once**. No shadow gate. No “green except …”. Do not list `test` and `coverage` as sibling prerequisites — that runs the suite twice.

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

## 16. `AGENTS.md` is the playbook distill — opt-out is first-class

**Problem:** Skill template assumed `sync_agents_md.py --check` ownership; P0-12 requires a short playbook distill (<~80 lines) with “never write to an audited target”, etc.

**Solution:** This repo is **opt-out** ([guardrails.md](../.agents/skills/dev-protocol/guardrails.md) §6): root `AGENTS.md` is hand-written from `roadmap/agent-playbook.md`. `scripts/sync_agents_md.py` has `MODE=opt-out` — `--check` is a no-op, a write is refused. Pre-commit omits agents-md-sync. Do not regenerate.

**Invariant:** Keep `AGENTS.md` short, linked to playbook + metrics spec, with the hard guardrails verbatim in spirit. Never run the generator in a way that drops product rules.

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

## 22. Layering: `synthetic/` never imports `adapters/`

**Problem:** Putting `SyntheticAdapter` construction inside `synthetic/` would couple scenario specs to engine I/O and break import-linter.

**Solution:** `ScenarioSpec` lives in `synthetic/`; materialise `SyntheticAdapter` only in `adapters/` (`open_scenario` / registry).

**Invariant:** synthetic ⊬ adapters (and ⊬ core). Do not weaken `.importlinter`.

## 23. Tombstone empty ≠ live self-match query

**Problem:** Querying with a live corpus vector at `ef_search=1` always self-matches at distance 0 — never proves empty/tombstone filtering.

**Solution:** Query = coordinates of a tombstoned vector (or an external probe) with a tight `ef_search` / `ef_budget`.

**Invariant:** Empty-result tests must not use live self-match queries.

## 24. `DENIED_WRITE_NAMES` includes `add` — no `.add()` in adapters/core

**Problem:** `set.add` / list-shaped `.add()` trips `scripts/check_readonly.py` the same as engine write APIs.

**Solution:** Use `list.append`, dict literals, `|` on sets. Keep denylist attrs aligned with the AST script.

**Invariant:** Do not call `.add()` under `adapters/` or `core/`. Do not loosen the denylist.

## 25. IVF pure-Python k-means is expensive; first `@pytest.mark.slow` must stay selectable

**Problem:** Small IVF scenarios ≈ 8k points; under `--cov` clocks blow past `<20s`. Also, a harness that requires “slow collects nothing” breaks once the first slow test exists.

**Solution:** Mark heavy build/search `@pytest.mark.slow`. Keep smoke of build without wall-clock in the default suite. Default `addopts` excludes slow; `verify-full` must allow selecting slow tests.

**Invariant:** Do not require empty slow collection. Do not put 8k IVF timing asserts in the default gate.

## 26. Contract suite: zero skips; False capability → `None` → `UNAVAILABLE`

**Problem:** Skipping unsupported capability paths hides regressions; inventing `0.0` for missing counts is the worst product bug.

**Solution:** Parametrised `tests/contract/` over the registry. Unsupported → adapter returns `None` → metric `UNAVAILABLE`. New adapter = register only.

**Invariant:** No skips for “unsupported”. Capabilities default False.

## 27. Oracle never optimised; production never imports `tests.oracle`

**Problem:** A fast “naive” reference stops being an independent check. Importing it from `vhecfsck/` couples product to test assets.

**Solution:** `tests/oracle/reference.py` stays slow and obvious. If a test is slow, shrink the input. import-linter forbids `vhecfsck` → `tests` / `tests.oracle`.

**Invariant:** Never speed up the oracle. Never import it from production.

## 28. Blocked GT: clamp L2 before sqrt; block-size invariance is the highest-value test

**Problem:** float32 cancellation yields ~`-1e-7` squared distances → `nan` poisons a whole GT row. Block-boundary merge bugs are invisible in aggregates.

**Solution:** `exact_knn` clamps squared L2 to ≥0 before `sqrt`. Tests assert identical results at B ∈ {1, 7, 999, n}. float16 is upcast on read; accumulation is float32 minimum (ADR-0005).

**Invariant:** Never skip the clamp test or the block-size invariance test. Do not hardcode B — derive from `working_set_mb`.

## 29. Coverage meta-tests must track new `core/` modules

**Problem:** `test_harness_config` subprocess coverage only ran a fixed target list; after `ground_truth.py` landed, overall dipped under 80% and core under 90% inside that meta-test (and pytest-cov can print FAIL at 89.89% while still exiting 0 — do not trust the banner alone).

**Solution:** Extend `_COVERAGE_TARGETS` with `tests/oracle/test_ground_truth.py` (or equivalent that executes new core code). Core-scoped meta-test must run those tests, not only an import smoke.

**Invariant:** When you add lines under `vhecfsck/core/`, update the coverage meta-targets in the same ticket. Never lower floors.

## 30. Do not invent perf budgets; P8-04 owns measured numbers

**Problem:** Ticket text cites `release-plan.md` budgets that are still empty cells (“metric to publish”).

**Solution:** Perf tests may exercise scale / opt-in 1M (`VHECFSCK_PERF_1M=1`) and assert completion + shape. Absolute wall/RSS thresholds wait for measured P8-04 values.

**Invariant:** Never write a performance number into docs or asserts that nobody measured on a named reference machine.

## 31. Canary self-exclusion: strip query id from GT **and** returns

**Problem:** With corpus-drawn queries and `self_exclude=True`, excluding the query id from ground truth only still leaves self in `R_K` at distance 0 — `recall_dist` inflates (~1/k) even under exact search.

**Solution:** When `query_source_ids` + `self_exclude`, request `k+1` neighbours from `exact_knn`, drop the query id from GT, **and** replace matching ids in the engine return row with `-1` before scoring.

**Invariant:** Self-exclusion is symmetric: GT and returns must both omit the query's own id.

## 32. Oracle single-query fixtures vs Q<5 guard

**Problem:** Fixture A and most §2.5 edge-case tests use `Q=1`. The production guard `Q < 5 → UNAVAILABLE` blocks them.

**Solution:** `compute_canary_recall(..., enforce_min_queries=False)` for hand-verified oracle tests only. Default remains `True` for pipeline/CLI paths.

**Invariant:** Never weaken the guard globally; opt out explicitly in named oracle tests.

## 33. Tombstoned `returned_invalid` when adapter filters dead ids

**Problem:** `SyntheticAdapter` ivf_tombstoned post-filter drops dead ids from returns — `returned_invalid` stays 0 on real search even when path blocking exists.

**Solution:** Acceptance test splices a known-deleted id from the scenario into the return matrix. That encodes the diagnostic field for engines that leak tombstones; short_returns covers path blocking separately.

**Invariant:** Do not weaken the adapter to pass the metric test; inject the failure mode the metric is meant to detect.

## 34. `verdict.py` is table-tested; 100% branch coverage is mandatory

**Problem:** Verdict aggregation has many branches (UNAVAILABLE floor, strict mode, LOW-evidence FAIL cap, all-DISABLED).

**Solution:** P2-09 ships an exhaustive `_AGGREGATE_CASES` parametrized table plus `evaluate` direction pairs. Ticket requires **100% branch coverage** on `vhecfsck/core/verdict.py` — verify with `coverage run --branch`.

**Invariant:** Do not simplify aggregation logic to reduce branches; extend the table when adding rules.

## 35. New `core/` modules → extend `_COVERAGE_TARGETS` **and** `test_core_coverage_gate_passes`

**Problem:** After P2-05…P2-09, five new core modules landed; meta-tests only ran ground_truth until targets were extended per ticket.

**Solution:** Each core ticket added its test file to `_COVERAGE_TARGETS` in `tests/unit/test_harness_config.py` **and** to `_CORE_COVERAGE_TARGETS` (used by the `@slow` `test_core_coverage_gate_passes`). The fast test `test_coverage_targets_include_core_importing_modules` fails if a new `from vhecfsck.core` test file is omitted. Live floors are `make coverage`, not the nested subprocess.

**Invariant:** Same as §29 — both lists stay in sync when `vhecfsck/core/` grows. Do not move the nested pytest-cov tests back into the default marker set.

## 36. Never nest pytest-cov inside the default suite

**Problem:** `test_overall_coverage_gate_passes` / `test_core_coverage_gate_passes` spawned pytest+`--cov` over almost the whole suite. Combined with `make coverage` running the suite twice, `make verify` hit 10–20+ min, pegged CPU/RAM, and left orphan pytest children after Ctrl+C.

**Solution:** Those two tests are `@pytest.mark.slow` (`verify-full` / nightly). Default `make test` is `--no-cov`. `make coverage` is **one** instrumented pytest (`fail_under=80`) plus `coverage report --include='vhecfsck/core/*' --fail-under=90` on the same `.coverage` data. Fast contracts keep the floors and the target lists honest without re-entering pytest.

**Invariant:** Do not re-introduce nested pytest-cov in the default gate. Do not lower 80/90. Do not drop the static completeness scan when adding `core/` tests. Do not also run `make test` as a sibling of `coverage` inside `verify`.

## 37. `size="tiny"` is a real cardinality, not a synonym of `small`

**Problem:** P2-11 called `open_scenario(..., size="tiny")` while `ScenarioSize` was only `small|large`. `_n_for("tiny")` fell through to 8k and `_dims` used the large-ish branch (32d / 64 lists). Tests thought they were cheap; they were heavier than `small`.

**Solution:** `ScenarioSize` includes `tiny` (~80 vectors, ≤4 IVF lists, 8/16 dims). Named scenario `tiny` stays the 50-vector exact guard-floor fixture. Verdict tests of P1-08 stay on default `small`.

**Invariant:** A size literal that tests pass must change `n` / `d` / `n_lists`. Do not shrink P1-08 verdict fixtures to `tiny`.

## 38. `setup.sh clean` is checkout-scoped; tests must not self-kill

**Problem:** First `clean` used `pgrep -f pytest` / `pkill` and killed every pytest on the host — including a live `make verify` and, without a guard, the e2e suite that invoked `clean`.

**Solution:** `SETUP_SH_IN_TEST=1` skips signalling. Live `clean` matches `ps` lines that contain both `pytest` and this repo path, then SIGTERM then SIGKILL. No global `pkill`. Log copy says “process cleanup”, not the token `pkill` (source tests forbid that string).

**Invariant:** Never `pgrep -f pytest` / `pkill -f pytest` without a checkout path filter. Never signal when `SETUP_SH_IN_TEST=1`.

## 39. Determinism allowlist must include `metrics.detail.read_at`

**Problem:** DFI (and any metric that embeds `counts.read_at`) writes an ISO timestamp into `detail`. Stripping only `counts.read_at` leaves P2-11 red as soon as those tests actually run on a cheap size.

**Solution:** `FROZEN_VOLATILE_ALLOWLIST` includes `metrics.detail.read_at`; `_strip_volatile_fields` blanks that key per metric.

**Invariant:** New timestamps in report JSON join the frozen allowlist in the same ticket. Do not delete the allowlist test to silence a diff.

## 40. SPA Front-End Visualizer bundle is zero-egress and zero-Node for Python users

**Problem:** Including a web UI visualizer can accidentally introduce external CDN requests (egress risks) or require Node.js at `pip install` time.

**Solution:** Vite + TypeScript in `strict` mode with Vitest + `happy-dom` (`vhecfsck/web`). Bundled static output in `vhecfsck/web/dist` is packaged inside Python wheel/sdist. `dist/` is not committed to git repository; `make web-build` builds locally for dev checkout, while `vhecfsck serve` returns an actionable error if `dist/` is missing.

**Invariant:** All visualizer assets (fonts, icons, Three.js shaders) must be bundled locally with zero egress. Python end-users must never need Node.js.

## 41. Three test moments — do not collapse them into `make verify`

**Problem:** Agents treated `make verify` as the only legal verb: on every pull of `main` and
again at ticket close. Combined with `verify` listing both `test` and `coverage`, the UI
sat on “waiting for make verify” for ~10 min (suite twice: ~3:40 + ~6:22) and looked like a
loop. `AwaitShell` with a 4 min timeout made it worse.

**Solution:** Inner loop = the test you are writing (`make test` if you want the whole
uninstrumented default suite). Merge gate = `make verify` **once**; `coverage` is that suite.
Version tag = `make verify-full`. Recorded in `AGENTS.md` and the playbook.

**Invariant:** Do not add `test` back as a verify prerequisite. Do not run `make verify` just
because `main` was updated. Do not invent a fourth command for “related tests”.

## 42. LanceDB optional extra & `_rowid` scanner

**Problem:** `lance` on PyPI is a namespace package, whereas `pylance` installs the Python package providing `import lance`. Additionally, checking `importlib.import_module("lance")` alone succeeds when `pylance` is present even if `lancedb` is absent.

**Solution:** In `pyproject.toml`, `lancedb = ["pylance>=11.0.0", "lancedb>=0.37.1"]`. `LanceDBAdapter` checks both `lance` and `lancedb` modules on import, and uses `ds.describe_indices()` and `ds.stats.index_stats(name)` for non-deprecated metadata access.

**Invariant:** `lancedb` extra must require `pylance` + `lancedb`. Import checks verify both modules.

## 43. DirectorySnapshot & `chmod a-w` read-only harness

**Problem:** Standard file comparison after an audit may pass if a write failure is silently caught or swallowed by an engine.

**Solution:** In `tests/integration/test_readonly_lancedb.py` (P5-07), `DirectorySnapshot` records size, mtime, and SHA-256 for all files. Additionally, the audit runs against a dataset mounted read-only (`chmod -R a-w`).

**Invariant:** File-backed engine read-only tests must combine hash/mtime snapshot diffing with a `chmod -R a-w` read-only mount execution.

---

## 44. Visualizer never fabricates tombstone positions; fps is not a guessed constant

**Problem:** A translucent grey cloud of "deleted" points that nobody read would look
exactly like evidence. Asserting "60 fps" in docs without a named-machine measurement
would violate the empirical-metrics rule the same way.

**Solution:** `resolve_tombstone_layer` plus `assert_no_fabricated_tombstones` refuse to
emit class=TOMBSTONE points unless coordinates were actually read. The display budget
lives in `core.lod`; `docs/perf/visualizer.md` records the constant and that wall-clock
fps is P8-04's job. Progressive chunks reuse one projection (`AssembledScene`).

**Invariant:** Never invent tombstone coordinates. Never write a frame-rate into docs
that nobody measured. Front end renders buffers computed in `core/`; it does not
derive metrics.

---

## 45. Playwright E2E browser tests are dev-only and isolated from `make verify`

**Problem:** Including a browser test runner in `make verify` or committing `dist/` outputs causes merge inflation, slow gate times, or Node runtime requirements for Python users.

**Solution:** Playwright + `@axe-core/playwright` tests live in `vhecfsck/web/tests/e2e/*.spec.ts` with `testMatch: '**/*.spec.ts'` in `playwright.config.ts`. They run via `npm --prefix vhecfsck/web run test:e2e` (`make web-test-e2e`). Python gate `make verify` remains browser-free and fast.

**Invariant:** Playwright tests are strictly devDependencies. `make verify` does not invoke the browser.

---

## 46. Postgres adapter: `Cursor.stream`, never `.execute()`

**Problem:** `scripts/check_readonly.py` denies `.execute()` (and `.commit()`, `.upsert()`, …) under `adapters/` and `core/` with **zero** `# readonly-ok` exemptions (`test_guard_passes_on_clean_tree`). psycopg's normal read path is `.execute()`.

**Solution:** Session: `options="-c default_transaction_read_only=on"` plus `Connection.read_only = True`. Statement send: `Cursor.stream`. Session knobs via `SELECT set_config(...)`, not a write-shaped `SET`. Identifiers must match `^[A-Za-z_][A-Za-z0-9_]*$` so they are interpolated without quoting tricks.

**Invariant:** Do not add an exemption to land SQL. Do not put denied statement shapes (`DELETE FROM`, `INSERT INTO`, `VACUUM`, …) in adapter string constants — including comments that are actually string literals. Naive substring tests for `.execute(` fail on the module docstring (lessons 12/17); use `check_file`.

---

## 47. Qdrant DFI: only per-segment `num_deleted_vectors`

**Problem:** `points_count - indexed_vectors_count` looks like a tombstone count. It also excludes vectors in segments below the indexing threshold, so a freshly loaded clean collection reports fragmentation that does not exist (metrics spec §4.2).

**Solution:** Walk collection telemetry for `num_deleted_vectors`. If the field never appears, `report_deleted_counts=False` → DFI `UNAVAILABLE`. Never substitute the indexed gap.

**Invariant:** Honest capabilities over a convenient number. Pipeline sets DFI `proxy` when `report_deleted_counts and not deleted_counts_exact` (Postgres table-level `n_dead_tup`).

---

## 48. `Report` secret scanner vs `redact_secrets`

**Problem:** `redact_secrets` rewrites `postgres://user:pass@host` to `postgres://user:REDACTED@host` and `?api_key=` to `api_key=REDACTED`. `Report._validate_no_secrets` still matches `user:pass@` and `api_key=`, so a redacted P7 location cannot serialise.

**Solution:** Strip the token `REDACTED` from the dumped report before scanning. Live passwords still fail. Adapter `location` stays `redact_secrets(target)`.

**Invariant:** Do not skip the scanner. Do not put a live DSN in `TargetDescriptor.location`.

---

## 49. Injected engine fakes must match SDK keywords and terminate scans

**Problem:** Prefixing unused args (`def retrieve(self, _collection_name, ...)`) breaks `retrieve(collection_name=...)`. The adapter falls back and the test “passes” on the wrong path. A Postgres fake that always returns rows on `FETCH` makes `iter_live_vectors` hang.

**Solution:** Fake methods use the real keyword names. After one `FETCH`, return empty. Contract suite registers `qdrant_injected` / `postgres_injected` so this is not unit-only.

**Invariant:** Do not rename SDK kwargs to silence ARG002; `del name` or assert them. A scan/cursor fake must have an empty terminal page.

---

## 50. `make verify` must not have `[qdrant]` / `[postgres]` installed

**Problem:** `PostgresAdapter._maybe_register_vector` runs whenever `pgvector` is importable. A gate venv with `--extra postgres` calls `register_vector(FakePostgres)` → `TypeError`, nine contract ERRORs, and a red `make verify` that looks like a harness bug.

**Solution:** Gate sync is `uv sync --group dev` (today also `--extra lancedb`: those tests import `pyarrow` at module level). Engine extras only for `uv run pytest tests/integration`. Restore the gate venv before the next `make verify`. Do not teach the fake to satisfy `register_vector`.

**Invariant:** `[qdrant]` / `[postgres]` stay out of the venv that runs the gate. `--extra postgres` is not a harmless convenience (lesson 5 covers `--all-extras`; this is the single-extra version of the same trap).

---

## 51. Container harness: marker rewrite, skip≠CI, seed in `tests/`

**Problem:** Default addopts are `-m "not slow and not integration and not perf"`. `pytest tests/integration` would deselect P7-01. A Docker skip in CI would merge a suite that never ran. Seeding in `vhecfsck/` would be a write path (ADR-0001).

**Solution:** `tests/integration/conftest.py` drops `not integration` from `markexpr` when every arg is under that directory. No Docker → skip with an actionable message; `CI` / `GITHUB_ACTIONS` → `pytest.fail`. Images pinned in `tests/integration/containers.py`; wait strategies, not `sleep`. `SeedPlan` in `tests/integration/seeding.py` is shared. `CREATE EXTENSION vector` **before** `register_vector`. The session Postgres fixture exports `VHECFSCK_POSTGRES_DSN` so DSN-gated tests in that directory run against the throwaway server.

**Invariant:** `testcontainers` is `dev` (ADR-0018), never a product extra. Do not bind fixed host ports. Do not put churn SQL in `adapters/` or `core/`.

---

## 52. Hubness & partition variance scale with dimension d

**Problem:** Absolute static thresholds for `hub_share_top1pct` (0.20) and `antihub_fraction` (0.25) derived from source specs produce 100% false-positive rates on isotropic Gaussian controls for $d \ge 128$ because hubness naturally increases with dimension $d$.

**Solution:** In `vhecfsck/config.py`, threshold resolution applies per-dimensionality profiles (`low` $d \le 64$, `medium` $d \le 384$, `high` $d \le 1024$, `ultra_high` $d > 1024$). `vhecfsck/pipeline.py` calls `resolve_thresholds_for_dimension(effective, dimension)` while strictly preserving explicit user overrides (`AuditConfig.thresholds`). Measurements and error analyses are documented in `docs/calibration/thresholds.md` and ADR-0011.

**Invariant:** Never compare hubness metrics across different dimensions or sample sizes without applying dimension-calibrated profiles or checking comparability rules (`P8-03`).

---

### Lesson 53 (P8-05 Resource Ceilings & Graceful Degradation)

**Context:** High-dimensional vector audits on memory-constrained machines could risk OOM or thrashing if sample sizes are uncalibrated to available memory ceilings.

**Solution:** `_degrade_sampling` scales `queries` and `hubness_sample_size` proportionally when `max_memory_mb` is exceeded, appending `sampling_degraded_for_memory_budget` warnings and setting `truncated = True`. If memory budget is below minimum viable allocation (< 1 KB or scale < 0.0001), `ResourceError` (exit code `USAGE`/4) is raised. Peak RSS is captured in `RunContext.peak_rss_mb`.

**Invariant:** Resource limits must trigger explicit degradation with evidence downgrade or raise `ResourceError`; never allow unhandled OOM or unflagged truncated output.

---

### Lesson 54 (P8-06 Mid-Audit Connection Loss & Concurrency)

**Context:** Targets killed or network drops mid-audit could produce unhandled `ConnectionError`/`OSError` exceptions (exit code 70 internal error).

**Solution:** `vhecfsck/pipeline.py` wraps adapter calls in `_stage` and `_run_metric` to catch `(ConnectionError, OSError)` and raise `TargetConnectionError` (exit code `USAGE`/4) with actionable hints.

**Invariant:** Target connectivity failures during audits must always map to `TargetConnectionError` (exit code 4), never raw process crashes.

---

### Lesson 55 (P8-10 Read-Only Assurance & Network Egress)

**Context:** Infrastructure audit tools must guarantee zero network egress and zero state mutations across all engines.

**Solution:** `tests/integration/test_readonly_all.py` enforces filesystem hash/mtime invariance across LanceDB/Synthetic and monkeypatches `socket.socket.connect` to assert 0 external egress connections during `run_audit`. Documented in `docs/read-only.md` and `SECURITY.md`.

**Invariant:** `run_audit` must never attempt external network connections or mutate target index state.

---

### Lesson 56 (P9-02 MkDocs Strict Mode & External GitHub Links)

**Context:** `mkdocs build --strict` treats any unmapped `.md` file or broken relative link (e.g. `../../roadmap/adr/`) as a fatal build error.

**Solution:** Navigation structure in `mkdocs.yml` maps all documentation pages. Markdown files in `docs/` citing files in `roadmap/adr/` or `roadmap/phases/` use absolute GitHub URLs (`https://github.com/hbauzan/vhecfsck/blob/main/...`).

**Invariant:** All cross-document links in `docs/` pointing to root/roadmap files must use absolute GitHub URLs; `mkdocs build --strict` must build with 0 warnings.

---

### Lesson 57 (P9-02 YAML Hash Escaping in Nav Titles)

**Context:** Navigation titles in `mkdocs.yml` containing `#` (e.g., `Qdrant #7147`) are parsed as YAML inline comments if unquoted, corrupting the navigation key.

**Solution:** Quote any navigation title containing `#` as a string literal (e.g., `"Qdrant #7147"`).

**Invariant:** `mkdocs.yml` navigation keys containing hash characters must be quoted string literals.

---

### Lesson 58 (P9-02 Auto-formatting Generated Documentation Output)

**Context:** Programmatic reference generators (`generate_cli_docs.py`, `generate_schema_docs.py`, `generate_metrics_docs.py`) output code blocks inside markdown files. `test_lint_typing_config.py` runs `ruff format --check .` over the repository. Unformatted code blocks in generated `.md` files trigger test failures.

**Solution:** Reference generators invoke `subprocess.run(["uv", "run", "ruff", "format", str(OUTPUT_PATH)])` after writing their target markdown file.

**Invariant:** Documentation generator scripts must format their generated `.md` files using `ruff format` before exit.

---

### Lesson 59 (P9-03 Syncing Dependencies for `make verify`)

**Context:** Running `uv sync --group dev --group docs` without `--extra lancedb` removes `pyarrow` from the virtual environment, causing collection import errors in LanceDB integration tests during `make verify`.

**Solution:** Always include `--extra lancedb` when syncing dependency groups (`uv sync --group dev --group docs --extra lancedb`).

**Invariant:** Verification gate execution environment must preserve required extra dependencies for integration tests.

---

### Lesson 60 (Hero GIF/PNG Asset URLs & PyPI Release Metadata)

**Context:** The README GIF generator (`scripts/record_demo.py`) sampled palette colors at fixed pixel strides, causing 100% background color sampling and producing an all-black GIF. Relative markdown image links (`docs/assets/...`) break on PyPI (`https://pypi.org/project/vhecfsck/`). Crucially, PyPI long descriptions are frozen from package metadata generated at build/publish time (`hatch build`) and do not update dynamically from `git push`.

**Solution:** `_palette_from_frames` uses `np.unique` to select UI colors by frequency, and `record_demo.py` exports both `vhecfsck-demo.gif` and `vhecfsck-demo.png`. `README.md` and `docs/index.md` reference the raw GitHub CDN URL (`https://raw.githubusercontent.com/hbauzan/vhecfsck/main/docs/assets/vhecfsck-demo.gif`) so the hero asset renders across PyPI, GitHub, and GitHub Pages (`https://hbauzan.github.io/vhecfsck/`). Updating the PyPI landing page requires publishing the next patch version release (e.g. `v0.1.2`).

**Invariant:** Hero GIF generator must use frequency-based unique color palette selection and export PNG/GIF assets; public documentation hero GIF references must use absolute raw GitHub CDN URLs. PyPI long description updates take effect upon publishing a new package release artifact.

---

### Lesson 61 (TH-05 Bit-exact float32 vectorisation)

**Context:** The synthetic IVF k-means was 180.30s of a 284.59s suite. Replacing the row
loop with array code is only safe if the output is byte-identical, because the golden
report fixtures are downstream of every centroid. "Equivalent within tolerance" is not
good enough, and the fast spellings are not the exact ones.

**Solution:** Measured, per metric space and shape, which forms preserve the bits:

| Form | Bit-exact | Why |
| :--- | :--- | :--- |
| `np.sqrt(np.sum(diff*diff, axis=2, dtype=np.float32))` | **yes** | same float32 reduction as the scalar path |
| GEMM identity `\|q\|² + \|c\|² − 2qc` | **no** | max error 1.95e-3 — the obvious temptation |
| `np.argmin` | **yes** | reproduces "first minimum wins" tie-break exactly |
| `np.bincount` + `np.add.at` | **yes** | unbuffered accumulation in row order |
| `vectors[assignment == c].sum(axis=0)` | **no** | numpy uses pairwise summation |

Row chunking is arithmetic-neutral (each output element still reduces one vector/centroid
pair), so the panel band size is a pure memory knob. The claim is pinned on raw bytes by
`tests/oracle/test_ivf_build.py` against the loop preserved in
`tests/oracle/reference_ivf.py`, and the rejected GEMM identity is named in the code so it
is not reintroduced as an "optimisation".

**Invariant:** When vectorising float32 numerics whose output feeds a golden fixture,
prove byte equality against the implementation being replaced before trusting it — and
prove it with `.tobytes()`, not a tolerance. Never substitute the GEMM distance identity
for an explicit `sqrt(sum(diff*diff))`, and never replace sequential accumulation with a
masked reduction.

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
