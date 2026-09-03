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

**Do not reopen:** TH-01, TH-02, TH-03, TH-04, TH-05, TH-06, TH-07, TH-08, MI-03, MI-04, MI-06, MI-07, P8-03, P9-10, P9-11, P9-12. ADR-0012 public copy is closed (H = Hector, wordplay — not Health).

**Do not start** P9-10 (`cancelled`). Do not start P9-09 unless you have a **real Linux host** (not Docker-on-Mac as the only witness). TH-09 is first. P10 stays unplanned.

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
| 8 | **TH-09** | `todo` ← **first** | Mypy × numpy 2.5.2 stubs on Python 3.12. Reproduce, then fix. Do not weaken the two mypy tests. |
| 9 | **P9-09** | `todo` | Linux port of `setup.sh`. Needs a real Linux host. No product version bump. |
| — | P9-10 | `cancelled` | Filler from the private-repo era. Hosted CI already runs Linux × 3.11/3.12/3.13. |

Contracts live in [`backlog.md`](backlog.md), in
[`archive/plans/`](archive/plans/) and [`archive/phases/`](archive/phases/),
and in the sections below (TH-09, P9-09, MI, TH done). Completed P0–P9 phase files
are archived; do not start `P0-01`.

---

## TH-09 — mypy × numpy 2.5.2 stubs on Python 3.12 (`todo`)

**Depends on:** TH-08 finding (out of scope then). **Size:** M.
**Touches:** `tests/unit/test_lint_typing_config.py`, possibly `[tool.mypy]`,
possibly a numpy / stub pin — **ADR if any dependency changes**.

**First ticket.** Do not start P9-09 in the same session.

**Symptom (TH-08, not re-measured here).** On Apple Silicon arm64 / macOS 26.5.1 /
Python 3.12.13 / numpy 2.5.2 / coverage 7.16.0, the two subprocess mypy tests
failed. Same under C tracer and sysmon — not a tracer effect. The tests:

- `test_mypy_reports_zero_errors`
- `test_mypy_rejects_untyped_function_in_core`

in `tests/unit/test_lint_typing_config.py`. They shell out to
`python -m mypy vhecfsck` and `python -m mypy vhecfsck/core`.

**Lock fact:** `uv.lock` installs numpy **2.4.6** when
`python_full_version < '3.12'` and numpy **2.5.2** when `>= '3.12'`. The Darwin
default gate venv is 3.11 (numpy 2.4.6) and is green.

**CI fact:** Linux `ci.yml` `make verify` on 3.12 is green on `origin/main`
`407ca4c`, including workflow_dispatch
[run 33699170199](https://github.com/hbauzan/vhecfsck/actions/runs/33699170199).
Do not assume the failure is universal. First job is **reproduce**.

**Do this, in order**

1. Do **not** replace the 3.11 `.venv` that runs the Darwin gate. Use an isolated
   3.12 env (`UV_PROJECT_ENVIRONMENT` or a throwaway directory). Sync:
   `uv sync --group dev --group docs --extra lancedb`. Never `--all-extras`.
   Never `--extra qdrant` / `--extra postgres`.
2. Run only those two tests. Capture **full** mypy stdout/stderr. Put the exact
   errors in the delivery report. Do not guess. Do not invent a count.
3. Compare with `uv run mypy vhecfsck` on 3.11 (expect 0) and with CI 3.12 (green).
4. Investigate: numpy 2.5.2 stubs vs pinned mypy vs `[tool.mypy] python_version = "3.11"`
   vs Darwin vs Linux. Inspect the pinned versions (guardrail 10).
5. Fix the **cause**. Acceptable: mypy config that stays `--strict` on
   `core`/`models`/`adapters`; a typed wrapper; a version pin **with an ADR**; a
   stubs resolution that `uv lock` records.

**Forbidden**

- Weaken, skip, `xfail`, or delete those two tests.
- `# type: ignore` without a reason comment.
- `ignore_missing_imports` on `numpy` as a convenience (numpy ships stubs).
- Raise `requires-python` without an ADR.
- Set `core = sysmon` in `pyproject.toml`.
- Lower floors 80/90. Nest pytest-cov. Shrink N (TH-03 cancelled).
- CHANGELOG `[Unreleased]` (not product). Do not bump `project.version`.

**If it does not reproduce** on a clean 3.12 lock sync: close the ticket as an
environment artefact (same class as lesson 62 / `ps` in a sandbox), with the
command lines and exit codes as evidence. Do not "fix" a green gate.

**Acceptance**

- [ ] Reproduction log (or non-reproduction log) in the delivery report.
- [ ] If reproduced: both mypy tests pass on 3.11 **and** 3.12 with the lock.
- [ ] `make verify` green **once** on the agent's Darwin 3.11 gate venv.
- [ ] Dependency move → ADR in the same ticket.

**Out of scope:** P9-09, P10, thresholds, `verdict.py`, `ground_truth.py`,
`docs/calibration/`, `vhecfsck/config.py`.

---

## P9-09 — Linux port of `setup.sh` (`todo`)

**Depends on:** P0-15 (`done`). Product already published (`0.1.3`).
**Size:** S. **Touches:** `setup.sh`, `tests/e2e/test_setup_sh.py`,
`CONTRIBUTING.md` (the macOS-only sentence), the header comments in `setup.sh`.
P0-15's Darwin-only clause in
[`archive/phases/phase-0-foundation.md`](archive/phases/phase-0-foundation.md)
is historical — do not rewrite it as if Linux was always allowed; this ticket
supersedes it going forward.

**Second in the queue.** Take it only when TH-09 is `done`. Canonical contract
is this section (the archived P9 phase file points here).

**Hard start condition.** You must have a **real Linux host** (Ubuntu or Fedora,
bash). WSL2 counts if `uname -s` is `Linux`. **Docker-on-macOS is not the
acceptance host** (it is not a contributor login console; the TTY installer
path differs). A "should work" port from Darwin memory is out of scope. If you
only have macOS, **stop** and leave this ticket `todo`.

**What this is.** Contributor console for a git checkout. Lesson 1: not a
process supervisor. **Not the product.** Hero remains `uvx vhecfsck demo`,
which already runs on Linux. CI already runs `make verify` on `ubuntu-latest` ×
3.11/3.12/3.13. Users who only `uvx` / `pip install` never see `setup.sh`.

### Version bump: no

Do not change `pyproject.toml` `version`. Do not tag. Do not add CHANGELOG
`[Unreleased]`. `setup.sh` is not in the wheel. Linux product support already
exists. A patch like `0.1.4` for this ticket would imply a product change that
did not happen. If the owner later wants a docs-only release, that is a
**separate** ticket.

### Contract

1. `require_macos` (or equivalent) accepts `Darwin` **and** `Linux`. Any other
   `uname -s` (Windows / `MINGW64_NT` / …) still exits `3` (INCONCLUSIVE) and
   names the supported OSes. Never fake healthy on an unsupported OS (lesson 3).
2. Stay Bash **3.2-safe** (stock macOS bash). Linux bash 4+ features
   (`mapfile`, `|&`, associative arrays) are forbidden.
3. Same menu, same Hitchhiker labels, same exit codes (`0` / `2` / `3` / `4`).
   Invalid-input line unchanged. No new menu item. **Do not** add a Docker verb
   (P9-10 is `cancelled`).
4. No daemon, no `.pids/`, no `logs/`, no Vite, no Hugging Face, no `nohup`, no
   `uvicorn` in the script, no `pkill` (lesson 38; existing tests).
5. `uv` missing: official installer
   `curl -LsSf https://astral.sh/uv/install.sh | sh`, `[y/N]` on a TTY.
   Non-interactive / `SETUP_SH_SKIP_PREREQ_PROMPT=1` → docs URL, exit `3`.
   Do not `apt-get install uv`. Do not `pip install uv`. Do not Homebrew-on-Linux.
6. `refresh_path`: keep `~/.local/bin` (Linux default for the official
   installer). Homebrew paths on Linux are harmless; do not require Homebrew.
   Do not prepend over an explicit `PATH` (lesson 4).
7. **Sync line must match the gate:**
   `uv sync --group dev --group docs --extra lancedb`.
   Today `cmd_sync` omits `--group docs`; `./setup.sh verify` runs `make verify`,
   which includes `tests/unit/test_docs_generation.py` (`mkdocs build --strict`,
   lesson 56). Extend `test_sync_invokes_uv_sync_without_all_extras` so the
   recorded args include `docs`. Never `--all-extras`. Never `--extra qdrant` /
   `--extra postgres` (lessons 5 / 50 / 59).
8. `demo` still exits **2** on the default tombstoned scenario (lessons 3 / 68).
   Do not change demo to exit 0.
9. `clean` still uses `scripts/clean_orphans.py`. Lesson 62: `test_clean_orphans.py`
   fails if the sandbox blocks `ps` — environment artefact, not a repo failure.
   Do not reopen P9-13.
10. Record the host: commit a small fixture (e.g.
    `tests/e2e/setup_sh_linux_host.txt`) with `PRETTY_NAME` from `/etc/os-release`,
    `bash --version`, `uname -s`. Not a placeholder. Tests on Darwin must not
    require that file to match the current runner — it is evidence of the
    measured port, not a matrix. Do not invent a distro matrix.

### Tests first (`tests/e2e/test_setup_sh.py`)

- Flip `test_linux_is_inconclusive_until_publish_port`: `SETUP_SH_UNAME=Linux`
  `./setup.sh help` exits **0**, same banner and labels as Darwin. Rename the
  test so the name matches the new contract.
- Add: an unsupported `uname` (`Windows` or `MINGW64_NT`) still exits `3`.
- Sync test requires `--group docs` and still forbids `--all-extras`.
- Existing Hitchhiker / no-SaaS / no-daemon tests stay green on Darwin.

### Acceptance

- [ ] On the recorded Linux host: `./setup.sh help` exits 0; `./setup.sh sync`
      exits 0 with the gate sync line; `SETUP_SH_IN_TEST=1 ./setup.sh clean`
      exits 0.
- [ ] On that host: `uv run pytest tests/e2e/test_setup_sh.py` green.
- [ ] On Darwin: the same file green (Linux is no longer exit 3).
- [ ] `make verify` green **once** (Darwin gate).
- [ ] `CONTRIBUTING.md` no longer says Linux is deferred / macOS-only.
- [ ] Host fixture committed, not guessed.
- [ ] `project.version` unchanged.

**Out of scope:** Docker local matrix (P9-10 cancelled). Nightly. A `ci.yml` job
for `setup.sh`. Windows console. Product CLI. Thresholds. `verdict.py`.
`ground_truth.py`. P10. PyPI publish. Tags.

**Guardrails:** lessons 1, 3, 4, 5/50/59, 8/41, 38, 56, 62, 68.

---

## P9-10 — Local Linux `make verify` in Docker (`cancelled`)

Leftover filler from when Actions were billed on a private repo. Hosted
`.github/workflows/ci.yml` already runs `make verify` on `ubuntu-latest` ×
Python 3.11 / 3.12 / 3.13. Do not implement a Docker verb on `setup.sh`. Do not
add a second `push` / `schedule` workflow. The commented recipes in `ci.yml`
stay as copy-paste; they are not this ticket.

---

## P9-11 residual — Node 20 witness (`done`)

Pins were already on Node 24-era majors. Witness
`gh workflow run ci.yml` (no tag):
[run 33699170199](https://github.com/hbauzan/vhecfsck/actions/runs/33699170199)
(`workflow_dispatch` on `407ca4c`, conclusion success).
`gh run view 33699170199 --log | grep -i "node.js 20"` was **empty**.
`release.yml` dispatch without a tag was already done (run 33698069648; publish
skipped). Do not reopen. Do not cut a test tag.

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
- Public name: H is **Hector** (wordplay), not Health. Do not invent a different
  expansion (ADR-0012 closed).

P9-11 Node-20 residual is **done** (run 33699170199; grep empty). P9-10 is
`cancelled`. Next: TH-09, then P9-09.
