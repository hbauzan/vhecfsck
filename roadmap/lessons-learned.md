# LESSONS LEARNED & ARCHITECTURAL INVARIANTS

**Este archivo es la memoria de handoff entre agentes de `vhecfsck`.** Vive en
`roadmap/`, no dentro del pack `dev-protocol`. Solo queda lo **activo**: estado,
critical path, reglas de entorno/gate, invariantes P8+, y un índice de P0–P7.
Los write-ups históricos de P0–P7 están en
[`archive/lessons-learned-historical.md`](archive/lessons-learned-historical.md).

El pack solo trae el template y el protocolo de lectura/escritura:
[`.agents/skills/dev-protocol/lessons-learned.template.md`](../.agents/skills/dev-protocol/lessons-learned.template.md)
§5. Se **lee** cuando entrás en frío o cuando una decisión concreta depende de
una invariante, y se **escribe** cuando el usuario pide un handoff. Ninguna de
las dos por reflejo.

Cola de implementación: [`next-ticket.md`](next-ticket.md). Un ticket, en orden.

---

## 0. Estado

**P0–P7 completos.** Contratos de ejecución archivados en
[`archive/phases/`](archive/phases/). No los reabras.
**P8 completo** en `main` (P8-01…P8-11, incluido **P8-03** baseline/delta). No lo
reinicies: un §0 viejo que lo listaba como critical path está stale.
**P9** casi cerrado: P9-01…P9-08 y P9-11/13/14 `done`. Fase archivada en
[`archive/phases/phase-9-docs-release-and-launch.md`](archive/phases/phase-9-docs-release-and-launch.md).
P9-12 `blocked` (humano: env GitHub `pypi` + publisher PyPI). P9-09 `blocked`
(go-ahead + Linux real). P9-10 skip (CI Linux × 3.11/3.12/3.13 ya corre).
**MI-01 / MI-02 / MI-05 / MI-07 `done`.** Hubness self-query + freeze IVF drifted +
`inject_hubs` concentra ≥1% de masa (d=64). `S_Nk` in hubness `detail` (informative;
JSON `null` when `std(N_k)=0`). Reference calibration republished:
`synthetic-hubby` n=8020 `hub_share 0.9297 FAIL` / `antihub 0.6450 FAIL` /
overall WARN (evidence LOW, `|S|<10000`). `synthetic-drifted`
`partition_size_cv 0.9160 OK` — FNR still unmeasured. Healthy Gaussians are
`OK` under per-dimension profiles. `sentence-minilm` skipped (no cache npy).
**TH-06 / TH-07 / TH-04 / TH-08 `done`.** Batched exact_knn merge; in-process
`PrebuiltIvf` reuse; local `.coverage` cache (CI still traces); `COVERAGE_CORE=sysmon`
on 3.12+ (3.11 keeps the C tracer).
**Horizon:** [`phases/phase-10-post-1.0-horizon.md`](phases/phase-10-post-1.0-horizon.md)
sigue en `roadmap/phases/` (no archivado).

**Critical path activo:** [`next-ticket.md`](next-ticket.md) —
P9-12 (blocked-on-human).
No tomes dos. No reabras TH-01/02/03/04/05/06/07/08, MI-03/04/06/07, P8-03.
No arranques P9-09 ni P9-10.

**HEAD de referencia:** `main` after merge of `perf/th-08-coverage-sysmon`.
Confirm with `git log -1 origin/main`.
**Remote:** `origin` → `https://github.com/hbauzan/vhecfsck` (**PUBLIC** desde P9-07).
Runners estándar de GitHub Actions son gratis en repo público.

**Licencia / atribución:** Apache-2.0; credit = **hbauzan**.
**Gate único:** `make verify` (lint + format-check + typecheck + coverage + layers
+ readonly). `coverage` is the suite; `make test` is the inner loop.
**CI:** `.github/workflows/ci.yml` corre `make verify` en Linux × Python
3.11/3.12/3.13. Sync = `uv sync --group dev --group docs --extra lancedb`
(**nunca** `--all-extras`, **nunca** `--extra qdrant` / `--extra postgres` —
lecciones 50 y 59). Residual P9-11: falta un `gh workflow run ci.yml` testigo
(`grep -i "node.js 20"` vacío) y un dispatch de `release.yml` **sin** tag.

**Producto:** auditor CLI read-only. Hero: `uvx vhecfsck demo`.
`setup.sh` es consola de contribuidor macOS, no el producto.

Residual dueño (no lo “arregles” vos solo):
- PyPI `0.1.3` está publicado; Trusted Publishing es **P9-12**, blocked-on-human.
  No secret PyPI. No tag de prueba.
- ADR-0012: la expansión de la `H` en copy público sigue abierta.

Las lecciones de `vhectorlab` **no** se copian.

---

## P0–P7 invariant index

Full Problem/Solution/Invariant write-ups:
[`archive/lessons-learned-historical.md`](archive/lessons-learned-historical.md).
The numbered lessons below remain in force. Environment and gate rules that
every remaining ticket hits are restated in full after the table.

| # | Invariant (one line) | Full text |
| ---: | :--- | :--- |
| 1 | Never turn `setup.sh` into a process supervisor. When `demo` (P3-05) or `serve` (P4-06) land, wire them as foreground CLI calls — do not add background lifecycle. | [`setup.sh` is a contributor console, not the product](archive/lessons-learned-historical.md) |
| 2 | Never let a Hitchhiker quote replace or outrank the technical action in the menu. Quotes stay in the dim parenthetical slot. | [Menu hierarchy: technical action primary, Hitchhiker secondary](archive/lessons-learned-historical.md) |
| 3 | Never fake a green health or a successful run for a feature that is not built yet. | [Missing capability is `INCONCLUSIVE` (exit 3), never fake-healthy](archive/lessons-learned-historical.md) |
| 4 | Tool discovery must not reorder an intentional `PATH`. | [Do not prepend Homebrew/`~/.local` over an explicit `PATH`](archive/lessons-learned-historical.md) |
| 5 | Default sync stays base (+ declared dependency groups). No `--all-extras` in setup or CI. | [Never `uv sync --all-extras` (setup.sh, CI, or “convenience”)](archive/lessons-learned-historical.md) |
| 6 | Do not grow `setup.sh` to host visualizer or deploy concerns. Follow the phase tickets. | [vhectorlab assets map to tickets, not to setup](archive/lessons-learned-historical.md) |
| 7 | Do not reintroduce nonexistent ruff override tables. Keep product trees clean; do not “fix” roadmap prose or skill templates to satisfy format-check. | [Ruff has no path `lint.overrides` — scope ANN+D with per-file-ignores](archive/lessons-learned-historical.md) |
| 8 | Leave every ticket with `make verify` green **once**. No shadow gate. No “green except …”. Do not list `test` and `coverage` as sibling prerequisites — that runs the suite twice. | [`make verify` is the only gate — do not invent a parallel one](archive/lessons-learned-historical.md) |
| 9 | Attribution = `hbauzan`. Visibility and PyPI publish are owner-gated. Do not invent the `H` expansion in ADR-0012. | [Copyright credit is `hbauzan`; GitHub stays private; PyPI claim is owner-gated](archive/lessons-learned-historical.md) |
| 10 | No concurrent writers on the same branch or on shared paperwork files. | [One ticket = one branch = one commit; never parallelize overlapping trees](archive/lessons-learned-historical.md) |
| 11 | No probe files in the tree at commit time. No knowingly-red merges to `main`. | [Never merge a red gate; clean probe leftovers before commit](archive/lessons-learned-historical.md) |
| 12 | Do not loosen the denylist of write attrs. Do not return to naive substring SQL matching. | [Read-only SQL guard matches statement shapes, not prose](archive/lessons-learned-historical.md) |
| 13 | Do not rename to “avoid the lint”. Do not add a redaction bypass. | [`vhecfsck/logging.py` is intentional — suppress A005, do not rename](archive/lessons-learned-historical.md) |
| 14 | Never lower coverage floors to make a meta-test pass. Never weaken product tests. | [Coverage floor tests must track the growing package](archive/lessons-learned-historical.md) |
| 15 | Metric logic stays in `core/`. Domain types in `models/` import no internal package modules. New packages must extend `.importlinter` in the same ticket that introduces them. | [Layering contracts need real packages; `models` stays a leaf](archive/lessons-learned-historical.md) |
| 16 | Keep `AGENTS.md` short, linked to playbook + metrics spec, with the hard guardrails verbatim in spirit. Never run the generator in a way that drops product rules. | [`AGENTS.md` is the playbook distill — opt-out is first-class](archive/lessons-learned-historical.md) |
| 17 | Read-only prose in `adapters/` and `core/` must avoid denied SQL keyword tokens as whole words. | [Adapter / models prose must not trip the SQL readonly guard](archive/lessons-learned-historical.md) |
| 18 | Redact at the boundary that builds the descriptor. Do not pull `logging` or pydantic into `models/` without an ADR. | [`TargetDescriptor.location` is pre-redacted; models stay a leaf](archive/lessons-learned-historical.md) |
| 19 | Do not rely on numpy reduction helpers in coverage-sensitive asserts when a byte/scalar check suffices. | [Coverage + numpy: avoid reduction asserts that re-enter `numpy/__init__`](archive/lessons-learned-historical.md) |
| 20 | Module-purge import discipline tests belong in a fresh interpreter, not in-process. | [Never purge `numpy` from `sys.modules` in the parent pytest process](archive/lessons-learned-historical.md) |
| 21 | Pathology operators must induce the claimed geometry; tests verify by brute force, not by trusting placement labels. | [Synthetic hub placement: cluster centroids, not empty midpoints](archive/lessons-learned-historical.md) |
| 22 | synthetic ⊬ adapters (and ⊬ core). Do not weaken `.importlinter`. | [Layering: `synthetic/` never imports `adapters/`](archive/lessons-learned-historical.md) |
| 23 | Empty-result tests must not use live self-match queries. | [Tombstone empty ≠ live self-match query](archive/lessons-learned-historical.md) |
| 24 | Do not call `.add()` under `adapters/` or `core/`. Do not loosen the denylist. | [`DENIED_WRITE_NAMES` includes `add` — no `.add()` in adapters/core](archive/lessons-learned-historical.md) |
| 25 | Do not require empty slow collection. Do not put 8k IVF timing asserts in the default gate. | [IVF pure-Python k-means is expensive; first `@pytest.mark.slow` must stay selectable](archive/lessons-learned-historical.md) |
| 26 | No skips for “unsupported”. Capabilities default False. | [Contract suite: zero skips; False capability → `None` → `UNAVAILABLE`](archive/lessons-learned-historical.md) |
| 27 | Never speed up the oracle. Never import it from production. | [Oracle never optimised; production never imports `tests.oracle`](archive/lessons-learned-historical.md) |
| 28 | Never skip the clamp test or the block-size invariance test. Do not hardcode B — derive from `working_set_mb`. | [Blocked GT: clamp L2 before sqrt; block-size invariance is the highest-value test](archive/lessons-learned-historical.md) |
| 29 | When you add lines under `vhecfsck/core/`, update the coverage meta-targets in the same ticket. Never lower floors. | [Coverage meta-tests must track new `core/` modules](archive/lessons-learned-historical.md) |
| 30 | Never write a performance number into docs or asserts that nobody measured on a named reference machine. | [Do not invent perf budgets; P8-04 owns measured numbers](archive/lessons-learned-historical.md) |
| 31 | Self-exclusion is symmetric: GT and returns must both omit the query's own id. | [Canary self-exclusion: strip query id from GT **and** returns](archive/lessons-learned-historical.md) |
| 32 | Never weaken the guard globally; opt out explicitly in named oracle tests. | [Oracle single-query fixtures vs Q<5 guard](archive/lessons-learned-historical.md) |
| 33 | Do not weaken the adapter to pass the metric test; inject the failure mode the metric is meant to detect. | [Tombstoned `returned_invalid` when adapter filters dead ids](archive/lessons-learned-historical.md) |
| 34 | Do not simplify aggregation logic to reduce branches; extend the table when adding rules. | [`verdict.py` is table-tested; 100% branch coverage is mandatory](archive/lessons-learned-historical.md) |
| 35 | Same as §29 — both lists stay in sync when `vhecfsck/core/` grows. Do not move the nested pytest-cov tests back into the default marker set. | [New `core/` modules → extend `_COVERAGE_TARGETS` **and** `test_core_coverage_gate_passes`](archive/lessons-learned-historical.md) |
| 36 | Do not re-introduce nested pytest-cov in the default gate. Do not lower 80/90. Do not drop the static completeness scan when adding `core/` tests. Do not also run `make test` as a sibling of `coverage` inside `verify`. | [Never nest pytest-cov inside the default suite](archive/lessons-learned-historical.md) |
| 37 | A size literal that tests pass must change `n` / `d` / `n_lists`. Do not shrink P1-08 verdict fixtures to `tiny`. | [`size="tiny"` is a real cardinality, not a synonym of `small`](archive/lessons-learned-historical.md) |
| 38 | Never `pgrep -f pytest` / `pkill -f pytest` without a checkout path filter. Never signal when `SETUP_SH_IN_TEST=1`. | [`setup.sh clean` is checkout-scoped; tests must not self-kill](archive/lessons-learned-historical.md) |
| 39 | New timestamps in report JSON join the frozen allowlist in the same ticket. Do not delete the allowlist test to silence a diff. | [Determinism allowlist must include `metrics.detail.read_at`](archive/lessons-learned-historical.md) |
| 40 | All visualizer assets (fonts, icons, Three.js shaders) must be bundled locally with zero egress. Python end-users must never need Node.js. | [SPA Front-End Visualizer bundle is zero-egress and zero-Node for Python users](archive/lessons-learned-historical.md) |
| 41 | Do not add `test` back as a verify prerequisite. Do not run `make verify` just because `main` was updated. Do not invent a fourth command for “related tests”. | [Three test moments — do not collapse them into `make verify`](archive/lessons-learned-historical.md) |
| 42 | `lancedb` extra must require `pylance` + `lancedb`. Import checks verify both modules. | [LanceDB optional extra & `_rowid` scanner](archive/lessons-learned-historical.md) |
| 43 | File-backed engine read-only tests must combine hash/mtime snapshot diffing with a `chmod -R a-w` read-only mount execution. | [DirectorySnapshot & `chmod a-w` read-only harness](archive/lessons-learned-historical.md) |
| 44 | Never invent tombstone coordinates. Never write a frame-rate into docs that nobody measured. Front end renders buffers computed in `core/`; it does not derive metrics. | [Visualizer never fabricates tombstone positions; fps is not a guessed constant](archive/lessons-learned-historical.md) |
| 45 | Playwright tests are strictly devDependencies. `make verify` does not invoke the browser. | [Playwright E2E browser tests are dev-only and isolated from `make verify`](archive/lessons-learned-historical.md) |
| 46 | Do not add an exemption to land SQL. Do not put denied statement shapes (`DELETE FROM`, `INSERT INTO`, `VACUUM`, …) in adapter string constants — including comments that are actually string literals. Naive substring tests for `.execute(` fail on the module docstring (lessons 12/17); use `check_file`. | [Postgres adapter: `Cursor.stream`, never `.execute()`](archive/lessons-learned-historical.md) |
| 47 | Honest capabilities over a convenient number. Pipeline sets DFI `proxy` when `report_deleted_counts and not deleted_counts_exact` (Postgres table-level `n_dead_tup`). | [Qdrant DFI: only per-segment `num_deleted_vectors`](archive/lessons-learned-historical.md) |
| 48 | Do not skip the scanner. Do not put a live DSN in `TargetDescriptor.location`. | [`Report` secret scanner vs `redact_secrets`](archive/lessons-learned-historical.md) |
| 49 | Do not rename SDK kwargs to silence ARG002; `del name` or assert them. A scan/cursor fake must have an empty terminal page. | [Injected engine fakes must match SDK keywords and terminate scans](archive/lessons-learned-historical.md) |
| 50 | `[qdrant]` / `[postgres]` stay out of the venv that runs the gate. `--extra postgres` is not a harmless convenience (lesson 5 covers `--all-extras`; this is the single-extra version of the same trap). | [`make verify` must not have `[qdrant]` / `[postgres]` installed](archive/lessons-learned-historical.md) |
| 51 | `testcontainers` is `dev` (ADR-0018), never a product extra. Do not bind fixed host ports. Do not put churn SQL in `adapters/` or `core/`. | [Container harness: marker rewrite, skip≠CI, seed in `tests/`](archive/lessons-learned-historical.md) |

---

## Environment and gate rules (still hit every ticket)

### 5. Never `uv sync --all-extras`

**Invariant:** Gate sync is `uv sync --group dev --group docs --extra lancedb`.
Never `--all-extras`. Never `--extra qdrant` / `--extra postgres` as a
convenience (also 50, 59). Python deps only via `uv`.

### 8. `make verify` is the only gate

**Invariant:** `make verify` once per ticket, green, never `--no-verify`. Do not
invent a second loose gate. `make test` is the uninstrumented inner loop.

### 10. One ticket = one branch = one commit

**Invariant:** Never parallelize overlapping trees. No push/merge to `main`
without explicit OK.

### 11. Never merge a red gate

**Invariant:** A pre-existing failure is a finding, not a reason to proceed.

### 37. `size="tiny"` is a real cardinality, not a synonym of `small`

**Invariant:** Do not shrink fixtures to `tiny` to make the suite faster
(TH-03 cancelled). Full text in the historical file.

### 41. Three test moments — do not collapse them

| When | Command |
| :--- | :--- |
| While coding (TDD) | `uv run pytest` on the tests you are writing. `make test` if you want the uninstrumented default suite. |
| Ticket ready to merge | `make verify` **once**. Coverage is the suite. |
| Version tag / `verify-full` | `make verify-full`. |

### 50. `make verify` must not have `[qdrant]` / `[postgres]` installed

**Invariant:** Those extras are for marked integration tests, not the default
gate. Installing them to "make verify greener" hides import-layering failures.

---

## Active invariants (P8+, TH, Pages, hubness)

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

**Context:** `mkdocs build --strict` treats any unmapped `.md` file or broken relative link (e.g. `../../roadmap/adr/`) as a fatal build error. A **nav entry whose file was deleted** is also a `--strict` warning (MI-07: leftover `gaussian-16.md` after `PROFILE_REFERENCE` dropped d=16). Extra pages not listed in nav are INFO only and do not fail the build.

**Solution:** Navigation structure in `mkdocs.yml` maps all documentation pages. Markdown files in `docs/` citing files in `roadmap/adr/` or `roadmap/phases/` use absolute GitHub URLs (`https://github.com/hbauzan/vhecfsck/blob/main/...`). When `make calibrate` adds or drops `docs/calibration/reports/*.md`, update the Calibration Data nav in the same ticket.

**Invariant:** All cross-document links in `docs/` pointing to root/roadmap files must use absolute GitHub URLs; `mkdocs build --strict` must build with 0 warnings. A nav key must not point at a missing file.

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

### Lesson 62 (clean_orphans ancestor exclusion)

**Context:** `scripts/clean_orphans.py` matched any process whose command line contained
both a build token (`make `, `pytest`, …) and the checkout path. Excluding only
`self` + `ppid` still killed the shell that invoked `make verify` when the `cd` was on
that command line.

**Invariant:** The orphan killer's exclusion set is the **full ancestor chain**, not
self+ppid. Do not drop `clean-proc` from `verify` to paper over a too-wide match.
`tests/unit/test_clean_orphans.py` fails in sandboxes that block `ps`; that is not a
repo failure.

---

### Lesson 63 (MkDocs leaf URLs on GitHub Pages)

**Context:** This Pages site 404s trailing-slash leaf URLs (`/releasing/` 404,
`/releasing` 200). A redirect plugin papers over it and is out of scope.

**Invariant:** `use_directory_urls: false`. Link the working form (no trailing slash).
Do not invent a redirect plugin.

---

### Lesson 64 (GitHub Action major pins)

**Context:** `setup-uv` since v8 has no floating `@vN` tag. Pinning `@v10` 404s;
`@v10.0.1` works. Other actions in this repo moved to current majors (checkout v7,
setup-python v7, …). `pypa/gh-action-pypi-publish@release/v1` stays on that moving
tag on purpose.

**Invariant:** Pin `setup-uv` to a full release. Do not "bump to @vN" without checking
that the tag exists.

---

### Lesson 65 (Cancelled TH ≠ open MI; hubness sample; IVF freeze)

**Context:** TH-01/02/03 are **cancelled** (GEMM not bit-exact; CTracer already on;
tiny fixtures forbidden). MI-01/02 were **todo** and are now **done**. Mixing those
lists reopened GEMM and `size="tiny"`. Separately: hubness is self-query on `S`, so
an attractor not in the sample cannot move `hub_share`; and `open_scenario` refitting
k-means on drifted hides `lance#4164`. `inject_hubs` must concentrate ≥1% of live mass
on a tight attractor at **high d** (~64); d=16 does not move the gated metric. FAIL +
UNAVAILABLE is overall FAIL only when evidence is not LOW (`|S|<10000` → WARN).

**Invariant:** Do not reopen cancelled TH tickets to "fix" hubness. Pathology operators
must move the **gated** metric on the sample the metric actually sees. Do not refit IVF
on a frozen drifted assignment. Do not patch `verdict.py` to chase exit 2 when evidence
is LOW. Do not shrink P1-08 fixtures to `tiny` (also lesson 37).

---

### Lesson 66 (coverage.py parallel-data glob)

**Context:** TH-04 first named the coverage-cache sidecar `.coverage.meta`.
`coverage report` then warned `Couldn't use data file '.coverage.meta': file is
not a database` because coverage.py treats `.coverage.*` as parallel data files
and tries to combine them.

**Invariant:** Never create a file matching `.coverage.*` except coverage.py's
own data. The sidecar is `.coverage-cache.json` (gitignored). Pinned by
`test_meta_filename_is_not_a_coverage_data_glob`.

---

### Lesson 67 (TH-04 cache is repeat-only; CI always traces)

**Context:** The backlog "sub-30s local `make verify`" was written when pytest-cov
was 488 s. After TH-05/06/07 the default suite is ~77 s without coverage and
~97 s with it. A cache cannot make the *first* run sub-30 s without shrinking
tests (TH-03 cancelled). TH-04 reuses `.coverage` only when the tree fingerprint
matches. `GITHUB_ACTIONS` / `CI` / `COVERAGE_CACHE=0` always instrument. `make
test` stays the uninstrumented inner loop; do not add `make verify-fast`.

**Invariant:** Merge/CI `make verify` keeps both floors (80 / 90) from **one**
instrumented pytest. Do not drop coverage from the merge command. Do not invent
a second loose gate. Do not raise `requires-python` without an ADR. TH-08
adopted `COVERAGE_CORE=sysmon` on 3.12+ inside `scripts/coverage_gate.py`;
Python 3.11 keeps the C tracer. Escape hatch: `COVERAGE_CORE=ctrace`. Do not
set `core = sysmon` in `pyproject.toml` (3.11 would warn and fall back).
`open_scenario`'s `PrebuiltIvf` cache is **process-local** — CLI subprocesses
still pay one k-means; do not add a disk IVF cache without invalidation.

---

## 5. Protocolo de Mantenimiento de Lecciones Aprendidas

Este archivo es caro de leer y fácil de arruinar. Si se lee por reflejo, se paga en cada sesión; si se escribe por reflejo, se llena de ruido y deja de servir para lo único que sirve: que la próxima IA arranque donde terminó la anterior.

### 5.1. Cuándo se LEE
El agente **DEBE** leerlo en estos tres casos, y no por defecto en el resto:
1. **Entrás en frío.** Sesión nueva sobre trabajo que no hiciste vos, retomada después de un handoff, o continuación después de compactar contexto. Es literalmente para lo que existe.
2. **Vas a diseñar algo nuevo.** Feature, módulo o build desde cero: leelo antes de decidir la forma, no después.
3. **Estás en la Fase 3 de un debug** ([debugging.md](../.agents/skills/dev-protocol/debugging.md)). Buena parte de los bugs son invariantes re-rotas; si una cubre el área, es una hipótesis que ya viene con evidencia y con fix conocido.

No hace falta para reviews, commits, sync de docs ni ediciones triviales.

### 5.2. Cuándo se ESCRIBE
**Solo cuando el usuario lo pide** — típicamente al preparar un handoff. Si descubriste una invariante durable, **proponéla en el reporte de entrega** y dejá que el usuario decida si entra. El criterio de admisión es alto: una invariante que un agente futuro no debe re-romper, en pocas líneas. Las tablas de mediciones y los hilos abiertos van a `current-research/` (si el repo lo usa), no acá.

### 5.3. Cuándo una lección ya no alcanza
Si un bug reincide sobre una invariante **que ya estaba escrita acá**, el problema no es de documentación: la prosa no enforcea nada. Esa invariante se ganó un guard estático o un test de regresión ([guardrails.md](../.agents/skills/dev-protocol/guardrails.md) §5). Anotarlo dos veces no la va a hacer cumplir.
