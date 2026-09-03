# Next ticket — dispatcher for agents

**Read this before opening any other ticket.** One agent, one ticket, in the
order below. Dependencies are not suggestions. When the ticket is done, mark it
`done` here and in [`backlog.md`](backlog.md), then stop and wait for OK to merge.

Phrase: `Usando dev-protocol, cerrá <ID>`. Protocol:
[`.agents/skills/dev-protocol/SKILL.md`](../.agents/skills/dev-protocol/SKILL.md).
Cold start: [`lessons-learned.md`](lessons-learned.md) §0, then this file.

---

## Freeze

| | |
| :--- | :--- |
| Repo | `https://github.com/hbauzan/vhecfsck` (public) |
| Base | `origin/main`. Must contain merge `3a3e609` (P9-13 + P9-14 + P9-11 + MI-01 + MI-02) **and** `roadmap/archive/` (completed P0–P9 files). If `archive/phases/` is missing, **stop and ask**. |
| Product | read-only CLI auditor. Hero: `uvx vhecfsck demo` |
| Gate | `make verify` **once** per ticket. Never `--no-verify`. |
| Sync | `uv sync --group dev --group docs --extra lancedb`. **Never** `--all-extras`. |
| Delivery | one branch, one conventional commit. No push/merge to `main` without explicit OK. |
| Metric logic | only in `core/`. |
| CHANGELOG `[Unreleased]` | product only: **MI-05** done. Remaining TH/P9: no. |

**Do not reopen:** TH-01, TH-02, TH-03, TH-04, TH-05, TH-06, TH-07, TH-08, MI-03, MI-04, MI-06, MI-07, P8-03, P9-12.

**Do not start** P9-09 or P9-10. They stay skipped (see queue).

---

## Queue

Take the **first** row whose status is `todo`. If it is `blocked`, you may only
do the work the ticket says is allowed while blocked; then stop. Never start two.

| # | ID | Status | Why this slot |
| ---: | :--- | :--- | :--- |
| 1 | **MI-07** | `done` | Regenerated `docs/calibration/` against current profiles. Hubby FAIL published; drifted `partition_size_cv` still below WARN. |
| 2 | **MI-05** | `done` | `S_Nk` in hubness `detail` (informative; JSON `null` when `std(N_k)=0`). |
| 3 | **TH-06** | `done` | Batched `_block_topk` + `_merge_queries_topk`. Bit-exact. No GEMM. |
| 4 | **TH-07** | `done` | Cached PrebuiltIvf for healthy/tombstoned/drifted. Do not shrink N. |
| 5 | **TH-04** | `done` | Local `.coverage` cache. CI/merge still one instrumented run, both floors. |
| 6 | **TH-08** | `done` | `COVERAGE_CORE=sysmon` on 3.12+ in the gate. 3.11 keeps the C tracer. |
| 7 | **P9-12** | `done` | Trusted Publishing live: GitHub env `pypi` + PyPI publisher + YAML `environment:`. |
| — | P9-09 | `blocked` ← **idle** | Skip until owner says "listo para publicar" **and** a real Linux host exists. |
| — | P9-10 | `todo` (skip) | Filler. CI already runs Linux × 3.11/3.12/3.13. Do not pick. |

Contracts live in [`backlog.md`](backlog.md) (P9-09, P9-10), in
[`archive/plans/`](archive/plans/) and [`archive/phases/`](archive/phases/),
and in the sections below (MI, TH). Completed P0–P9 phase files are archived;
do not start `P0-01`.

---

## MI-07 — regenerate reference calibration (`done`)

Ran `make calibrate` (`--profile reference`). Harness wrote CSV + `reports/` +
sensitivity + `datasets.md`. `sentence-minilm` skipped (`npy` not in cache).
FPR/FNR prose in `thresholds.md` / README "Known gaps" updated from that CSV.
`synthetic-hubby`: `hub_share 0.9297 FAIL` / `antihub 0.6450 FAIL`, overall WARN
(LOW evidence). `synthetic-drifted` `partition_size_cv 0.9160 OK` — FNR still
unmeasured. Healthy Gaussians are `OK` under per-dimension profiles. Thresholds
in `config.py` were not changed.

---

## MI-05 — `S_Nk` in hubness `detail` (`done`)

**Depends on:** P2-06 (`done`). **Size:** S. **Touches:** `vhecfsck/core/hubness.py`,
`roadmap/02-metrics-spec.md` §3.5, `tests/oracle/test_hubness.py`, CHANGELOG.

**Formula** (Radovanović, Nanopoulos & Ivanović, JMLR 11:2487–2531, 2010, §2):

```text
S_Nk = mean((N_k - mean(N_k))^3) / std(N_k)^3
```

Population moments (`ddof=0`), same convention as `partition_size_cv`. Informative
only: **no threshold, no verdict, no gating**. Logic in `core/` only.

If `std(N_k) == 0`, the value is undefined. Do not write `0.0`. Omit the key or
emit JSON `null` — never a substitute number (guardrail 3 / ADR-0004).

**Fixture B, computed by hand, not guessed.** `N_k = [1, 2, 1, 0]`:

- mean = 1
- deviations = `[0, 1, 0, −1]`; cubes = `[0, 1, 0, −1]`; mean of cubes = 0
- `std = sqrt(0.5)` (population)
- **`S_Nk = 0.0` exactly**

Assert that in `test_fixture_b_exact`. Cite the paper in `02-metrics-spec.md` §3.5
next to the other diagnostics (`max_nk`, histogram, MAD outliers).

CHANGELOG `[Unreleased]` → Added. Do not add a metric id or a threshold profile.

---

## TH-06 — vectorise `_merge_query_topk` (`done`)

**Depends on:** P2-04. **Plan:** [`plan_optimizacion_test_harness.md`](archive/plans/plan_optimizacion_test_harness.md).
**Size:** M. **Touches:** `vhecfsck/core/ground_truth.py`.

Replaced the per-query Python loop with batched `_block_topk` +
`_merge_queries_topk`. Bit-exact against the loop preserved in
`tests/oracle/reference_merge.py` (`.tobytes()`, ascending-id tie-break,
`-1` / `+inf` padding). `_score_block` untouched — no GEMM identity.

Measured on Apple Silicon arm64 / macOS 26.5.1 / Python 3.11.15 / numpy 2.4.6,
Q=N=20_000, D=32, k=10, `working_set_mb=256` (6 blocks). Median of 3
`exact_knn` runs: **4.210 s → 3.360 s**. Instrumented split (one run): merge
0.732 s (120_000 calls) → 0.164 s (6 calls); block top-k 3.069 s (120_000
calls) → 2.641 s (6 calls). The 1.88 s / 2.53 s figure in the original
instrumentation was stale on this machine; merge was 0.732 s of 4.596 s.

Do not shrink fixtures to `tiny`.

---

## TH-07 — reuse PrebuiltIvf across tests (`done`)

**Depends on:** TH-05 (`done`). **Size:** S.

`open_scenario` caches `PrebuiltIvf` for healthy / tombstoned / drifted keyed
by `(name, size)`, copy-in and copy-out. Drifted is snapshotted from the MI-01
freeze — `_fit_ivf` is never called. **Did not shrink N.** Goldens unchanged.

Measured on Apple Silicon arm64 / macOS 26.5.1 / Python 3.11.15 / numpy 2.4.6.
Default suite `--no-cov`: `_fit_ivf` **98 calls / 1.767 s → 58 / 0.332 s**.
healthy n=8000: 21 calls, 1.166 s → 3 / 0.164 s; tombstoned n=8000: 16 / 0.525 s
→ 3 / 0.093 s. Suite wall 78.50 s → 76.60 s (883 passed; +3 reuse tests).
Targeted healthy small ×3: 0.051–0.061 s each (1 fit) → 0.070 s then 0.002 s.
Remaining small fits are the reuse-test cache clear plus CLI subprocesses
(process-local cache). Drifted was already 0 fits after MI-01.

---

## TH-04 — local coverage cache (`done`)

**Depends on:** P0-04. **Size:** M.

`scripts/coverage_gate.py` is the `make coverage` body. Merge/CI
(`GITHUB_ACTIONS` / `CI`) always runs **one** instrumented pytest and both
floors (80 overall, 90 `core/`). Locally, an unchanged tree reuses `.coverage`
and only reports. `make test` is still the uninstrumented inner loop. No second
gate. `COVERAGE_CACHE=0` forces a trace. Did not drop coverage from `make verify`.
Did not lower floors. C tracer unchanged (TH-02 cancelled).

Measured Apple Silicon arm64 / macOS 26.5.1 / Python 3.11.15 / numpy 2.4.6 /
coverage 7.16.0 (`CTracer available: YES`). Default suite `--no-cov` 76.60 s vs
instrumented pytest-cov 96.95 s (**+20.35 s tax**). `coverage report` overall
0.52 s + core 0.14 s. Tree fingerprint 0.872 s. Repeat `make coverage` after
a green verify: **0.91 s** cache hit. The backlog "sub-30s local
gate" was stale: the suite itself is ~77 s (TH-03 cancelled). The cache makes a
repeat local `make coverage` skip pytest, not a faster first run.

---

## TH-08 — `COVERAGE_CORE=sysmon` (`done`)

**Depends on:** TH-04. **Size:** S.

On Python 3.12+ the instrumented child in `scripts/coverage_gate.py` sets
`COVERAGE_CORE=sysmon` unless that variable is already set (`COVERAGE_CORE=ctrace`
is the escape hatch). Python 3.11 is unchanged (C tracer). Did not raise
`requires-python`. Did not lower floors 80/90. CI/merge still always traces.
`make test` is still `--no-cov`.

Measured Apple Silicon arm64 / macOS 26.5.1 / Python 3.12.13 / numpy 2.5.2 /
coverage 7.16.0 (`CTracer available: YES`; `SysMonitor` usable with `branch =
false`). Instrumented default suite, two interleaved runs, `COVERAGE_CACHE=0`:

| core | run 1 | run 2 |
| :--- | ---: | ---: |
| C tracer | 121.112 s | 100.142 s |
| sysmon | 73.575 s | 80.459 s |

Mean **110.627 s → 77.017 s**. Warm pair 100.142 s → 80.459 s. Worst sysmon
(80.459 s) still beat best C tracer (100.142 s). Overall 88.62% (sysmon run 2:
88.64%); `core/` 95%. Same 2 mypy failures on that 3.12 venv in both cores
(numpy 2.5.2 stubs) — not a tracer effect; out of scope.

---

## P9-12 — Activate PyPI Trusted Publishing (`done`)

GitHub environment `pypi` has required reviewers = owner. PyPI trusted
publisher on the existing `vhecfsck` project: workflow `release.yml`,
environment `pypi`. `verify-and-build` now declares
`environment: {name: pypi, url: https://pypi.org/p/vhecfsck}`. YAML auth
unchanged (`id-token: write`, no `password`). `docs/releasing.md` no longer
has the "Current state" box; §6 is the manual fallback. No PyPI secret. No
test tag.

---

## Traps (this pass)

- Hubness is **self-query on S**. The attractor must be **in** the sample.
  `ids[:2000]` after append drops the hubs.
- `open_scenario` must not refit IVF on drifted: freeze centroids + assignment
  or `partitions()` sees a rebalanced index, not `lance#4164`.
- `inject_hubs` append-at-centroid does not move `hub_share`. Need ≥1% mass on
  a tight attractor, the rest diffuse, and **high d** (~64). d=16 does not move it.
- FAIL + UNAVAILABLE = overall FAIL **only if evidence is not LOW**. `|S|<10000`
  → LOW → WARN. Do not patch `verdict.py` to chase exit 2.
- TH-01/02/03 `cancelled` ≠ MI-01/02 (those are `done`). Mixing them reopened
  GEMM and tiny fixtures.
- `hatch_build.py` early-returns if `dist/index.html` exists. Fresh wheel:
  delete `dist/` and `make web-build`.
- Goldens: `tool_version` in `tests/fixtures/golden/` = `pyproject.toml`.
- Docs → roadmap: absolute GitHub URLs. Generated md: `uv run ruff format`.
- `tests/unit/test_clean_orphans.py` fails in sandboxes that block `ps`. Not a
  repo failure.
- Pages leaf: `/releasing` 200, `/releasing/` 404. `use_directory_urls: false`.
  Do not add a redirect plugin.
- `setup-uv` v8+: pin a full release (`v10.0.1`), there is no floating `@v10`.
- Default `vhecfsck demo` exits **2** (FAIL). GHA `bash -e` treats that as a
  failed job unless the smoke step allows 0–3 (lesson 68).

Residual (not a ticket): P9-11 still needs a `gh workflow run ci.yml` witness
with `grep -i "node.js 20"` empty. `release.yml` dispatch without a tag is
**done** (run 33698069648; publish skipped).
