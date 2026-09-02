# Historical lessons (P0–P7)

These write-ups were extracted from [`lessons-learned.md`](../lessons-learned.md)
so the live file stays short. **The invariants are still in force.** If a
remaining ticket touches the area, read the full lesson here before coding.

Live file: current state, P8+ lessons, environment/gate rules, and a one-line
index of everything below.

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
