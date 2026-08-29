# P8 — Calibration and Hardening

**Goal:** make the numbers trustworthy and the tool boring.

Up to this point every threshold has been inherited from the source specification without
independent evidence. That is the largest remaining risk in the project: a checker that cries
wolf gets removed from the pipeline, and a checker that stays silent through a real failure is
worse than nothing. This phase produces the measurements that justify the defaults, and the
engineering that makes a 1M-vector audit predictable.

**Entry criteria:** P5 and P7 complete (multiple real engines available for measurement).

**Exit gate**

```bash
make verify-full     # includes slow, integration, perf, mutation testing
```

---

## P8-01 — Reference dataset calibration harness

**Depends on:** P7 · **Size:** L · **Touches:** `scripts/calibrate.py`, `docs/calibration/`, `tests/perf/`

**Goal:** find out what healthy actually looks like.

**Contract**
- A harness that runs the full metric suite over a set of reference corpora and records
  results as committed data files:
  - **Uniform random Gaussian** at `d ∈ {64, 128, 384, 768, 1536}` — the theoretical
    reference point. Hubness rises with `d` here by construction, which makes it the control
    that proves the metric responds to dimensionality as expected.
  - **Public embedding benchmark datasets** (the standard ANN benchmark corpora: SIFT, GIST,
    GloVe, NYTimes, and a modern sentence-embedding set). Chosen for permissive licensing;
    record the licence and provenance of each in `docs/calibration/datasets.md`, and download
    on demand rather than committing data ([risk R13](../risk-register.md)).
  - **Synthetic corpora with known injected pathologies**, as the positive controls.
- Sweep `hubness_sample_size` ∈ {1k, 5k, 20k, 50k} and `k_hub` ∈ {5, 10, 20} to quantify the
  sampling sensitivity that [`02-metrics-spec.md §3.2`](../02-metrics-spec.md) warns about.
  Publish the resulting sensitivity curves — they are the honest answer to "why does my number
  change when I change the sample size?", and having that answer ready is what prevents a
  false-positive report from becoming a credibility problem.
- Output a committed CSV plus a short report per dataset, regenerable with one command.

**Acceptance criteria**
- [ ] Every reference dataset's licence permits this use and is recorded.
- [ ] Healthy baselines published for all five metrics across all reference corpora.
- [ ] Sampling sensitivity curves published for the hubness metrics.

---

## P8-02 — Calibrate and justify the default thresholds

**Depends on:** P8-01 · **Size:** M · **Touches:** `vhecfsck/config.py`, `docs/calibration/thresholds.md`, `roadmap/adr/0011-thresholds-and-baseline-mode.md`

**Contract**
- For each metric, compare the inherited default against the measured healthy distribution and
  the measured pathological distribution. Report separation: at the chosen threshold, what is
  the false-positive rate on healthy corpora and the false-negative rate on injected
  pathologies?
- Adjust defaults **only where the evidence demands it**, and record every change with its
  before/after numbers. Resist the temptation to tune thresholds so that all reference data
  passes — some public corpora are genuinely hubby, and reporting that honestly is the correct
  outcome.
- Publish, per metric: the healthy range, the recommended threshold, the measured error rates,
  and a plain statement of which conditions invalidate the default (dimensionality, metric
  space, sample size).
- Update [ADR-0011](../adr/0011-thresholds-and-baseline-mode.md) with the measurements.
- Ship per-dimensionality threshold profiles if the data shows a single global default cannot
  work — the likeliest outcome for the hubness metrics, since hubness is a function of `d`.

**Acceptance criteria**
- [ ] No default threshold remains unjustified by a measurement.
- [ ] `partition_size_cv` defaults are checked against real k-means output: healthy k-means on
      real data typically yields a CV well below the inherited `1.20` warn level, so verify
      that the threshold is neither trivially loose nor accidentally tight.
- [ ] The false-positive rate on healthy reference corpora is documented, whatever it is.

---

## P8-03 — Baseline and delta mode

**Depends on:** P8-02, P3-01 · **Size:** L · **Touches:** `vhecfsck/cli.py`, `vhecfsck/core/verdict.py`, `vhecfsck/models/report.py`, `tests/e2e/test_baseline.py`

**Goal:** the feature that makes the tool usable on a corpus whose absolute thresholds do not
apply — which, after P8-02, will be many of them.

**Contract**
- `vhecfsck audit --baseline baseline.json` compares against a recorded healthy report and
  gates on **change** rather than on absolute value: recall dropped more than `X` points, DFI
  rose more than `Y`, CV grew by more than `Z`.
- `vhecfsck baseline record --output baseline.json` captures the current state, with a warning
  that a baseline recorded from an already-degraded index bakes in the degradation.
- Comparability enforcement: refuse to compare when seed, `k`, `hubness_sample_size`, `k_hub`,
  metric space, dimension, or engine differ. Emit `not_comparable` with the specific field
  rather than silently comparing incomparable numbers
  ([`02-metrics-spec.md §3.2`](../02-metrics-spec.md)).
- Delta thresholds configurable and defaulted from the P8-01 measured run-to-run variance, so
  the gate sits above noise rather than at an arbitrary round number.
- Report includes both the absolute states and the delta states; the verdict may be driven by
  either or both (`--gate absolute|delta|both`).

**Tests first**
- Two audits of an unchanged index → all deltas within noise, verdict `OK`.
- An audit after injected churn → delta gate fires even where the absolute value is still
  under threshold. This is the case that motivates the feature.
- Any comparability mismatch → `not_comparable`, exit `3`, never a bogus comparison.

---

## P8-04 — Performance budgets

**Depends on:** P2-04, P5 · **Size:** M · **Touches:** `tests/perf/`, `docs/performance.md`, `.github/workflows/nightly.yml`

**Contract**
- `pytest-benchmark` suites with **asserted budgets**, not just recorded timings, for: ground
  truth at 100k/1M × 768, hubness at `S=20k`, projection at 1M, full audit end to end, and
  scene encode/decode.
- Budgets set from measurements on a named reference machine, with the machine's specification
  published so a user can scale the expectation to their own hardware.
- Nightly regression detection with a tolerance band; a regression opens an issue rather than
  failing the branch, since benchmark noise on shared CI runners would otherwise make the
  build unreliable.
- `docs/performance.md` publishes the real numbers: audit duration and peak RSS versus corpus
  size and dimension. A concrete measured table is one of the more persuasive things an
  infrastructure tool can show, and a vague claim is one of the least.

**Acceptance criteria**
- [ ] Every published number was measured on the reference machine and is reproducible.
- [ ] Budget assertions fail on a deliberate 2× slowdown.

---

## P8-05 — Resource ceilings and graceful degradation

**Depends on:** P2-10 · **Size:** M · **Touches:** `vhecfsck/pipeline.py`, `vhecfsck/core/ground_truth.py`, `tests/unit/test_resource_limits.py`

**Contract**
- `--max-memory-mb`: estimate the requirement before starting each stage; if it would exceed
  the ceiling, reduce the sample size, record the reduction, downgrade
  `evidence_strength`, and set the relevant `truncated` flag. Never proceed and hope.
- `--max-seconds`: a per-stage deadline with a global cap. On expiry, return what was computed
  with `truncated = true`, and mark the metric's evidence accordingly.
- Fail fast with a clear message when even the minimum viable sample exceeds the ceiling,
  rather than thrashing.
- Peak RSS recorded in the report so a user can size the next run from evidence.

**Tests first**
- A ceiling below the natural requirement triggers documented degradation, not an OOM.
- A truncated audit still yields a well-formed report with correct flags.
- A metric that had to degrade never reports `HIGH` evidence.

---

## P8-06 — Concurrency and chaos

**Depends on:** P5, P7 · **Size:** M · **Touches:** `tests/integration/test_chaos.py`

**Goal:** production indexes are being written to while we read them. Behave.

**Contract**
- Run audits while a background writer inserts, updates and deletes, and while compaction or
  optimisation runs concurrently.
- Required behaviour: never crash; never produce a silently wrong number; emit
  `snapshot_inconsistent` with counts of what shifted; complete or degrade explicitly.
- Kill and restart the target mid-audit: the tool must exit `4` with a clear connection error,
  not `70`, and not a partial report presented as complete.
- Verify the target is unharmed after every chaos run, using the P5-07 harness.

**Tests first**
- Concurrent write during audit → `snapshot_inconsistent` present, report well-formed.
- Concurrent compaction → no crash, target unharmed.
- Target killed mid-audit → exit `4`, actionable message.

---

## P8-07 — Mutation testing on the numeric core

**Depends on:** P2 · **Size:** M · **Touches:** `Makefile`, `.github/workflows/nightly.yml`, `docs/testing.md`

**Goal:** find out whether the tests actually test anything. Coverage says a line ran;
mutation testing says a wrong line would have been caught — which is the property that
matters for a tool whose output people act on.

**Contract**
- Run `mutmut` (or `cosmic-ray`) over `vhecfsck/core/` and `vhecfsck/models/`.
- Investigate every survivor. Threshold comparison operators, `ddof`, tie-breaking direction,
  and off-by-one in top-`k` selection are the specific mutants that **must** be killed —
  each corresponds to a real, plausible, silent wrongness.
- Set a mutation-score gate in the nightly workflow, at the measured level, and ratchet it
  upward over time rather than picking an aspirational number now.

**Acceptance criteria**
- [ ] Zero surviving mutants in `verdict.py` and in the threshold comparisons.
- [ ] Every remaining survivor is either killed or documented with a justification.

---

## P8-08 — Fuzzing and adversarial inputs

**Depends on:** P2, P3 · **Size:** M · **Touches:** `tests/property/test_fuzz.py`

**Contract**
- Hypothesis-driven fuzzing of every `core/` entry point: extreme dimensions (1, 4096),
  `n ∈ {0, 1, 2}`, `k ∈ {0, 1, n, n+1}`, duplicate vectors, zero vectors, huge and tiny norms,
  denormal floats, `NaN` and `Inf`.
- Every input must produce either a correct result or a typed `VhecfsckError` — never an
  `IndexError`, a `nan` in the output, or a hang.
- Fuzz the report parser with malformed and hostile JSON (`export` path), and the scene codec
  with truncated and corrupted buffers.
- A `NaN` reaching a metric value is treated as a bug, not a value, and raises `InternalError`.

**Acceptance criteria**
- [ ] No unhandled exception type escapes `core/`.
- [ ] No output field can ever be `NaN` or `Inf`, asserted at the serialisation boundary.

---

## P8-09 — Error message audit

**Depends on:** P0-05 · **Size:** S · **Touches:** `vhecfsck/errors.py`, all raise sites, `tests/e2e/test_error_messages.py`

**Contract**
- Review every user-reachable error against three requirements: it says what went wrong, it
  says what to do about it, and it does not leak a credential.
- Every `UNAVAILABLE` reason string names the missing capability and, where possible, the
  privilege or version that would provide it. "Unavailable" alone is an unactionable dead end
  and will generate support load.
- A test enumerates every registered error code and asserts each has a non-empty, distinct
  hint — table-driven, so a new error without a hint fails the build.

---

## P8-10 — Read-only assurance across all engines

**Depends on:** P5-07, P7 · **Size:** M · **Touches:** `tests/integration/test_readonly_all.py`, `SECURITY.md`, `docs/read-only.md`

**Goal:** the evidence package behind the project's central claim.

**Contract**
- Extend the P5-07 harness to every engine, with engine-appropriate invariants: file hashes
  and mtimes for LanceDB; collection state, segment count and version for Qdrant; transaction
  read-only enforcement plus `pg_stat` write counters for pgvector.
- Verify no privileged operation is even attempted: run against a `SELECT`-only PostgreSQL role
  and a read-only Qdrant API key, and confirm a clean audit with no permission errors — which
  proves the tool never asks for more than it needs.
- **Network egress test:** monkeypatch the socket layer and assert connections are made only
  to the configured target. No telemetry, no update check, no CDN font, no analytics — in the
  Python package and in the web bundle. A vendored font is a dependency; a remote font is an
  egress.
- `docs/read-only.md` documents exactly what is verified and how a reviewer can re-run it
  themselves.

**Acceptance criteria**
- [ ] All engines: zero observable state change after a full audit.
- [ ] Audits succeed with minimum-privilege credentials.
- [ ] Zero unexpected network connections from either the Python package or the web bundle.

---

## P8-11 — Supply chain and dependency review

**Depends on:** P0-10 · **Size:** S · **Touches:** `.github/workflows/security.yml`, `pyproject.toml`, `SECURITY.md`

**Contract**
- `pip-audit` for Python and `npm audit` for the front end, in CI, failing on high severity.
- Dependabot (or equivalent) for both ecosystems, grouped to avoid pull-request noise.
- Lock files committed for reproducible builds; `uv.lock` and `package-lock.json`.
- An SBOM generated at release time and attached to the GitHub release.
- Review the total dependency footprint and remove anything not carrying its weight — every
  transitive dependency is a package a security-conscious infrastructure team will read before
  installing next to their database.

---

## Phase exit checklist

- [ ] Every threshold justified by published measurement; false-positive rates documented.
- [ ] Baseline/delta mode working, with comparability strictly enforced.
- [ ] Performance budgets asserted, and real numbers published for 100k and 1M.
- [ ] Resource ceilings degrade explicitly and never OOM.
- [ ] Chaos suite: no crashes, no silent wrongness, targets unharmed.
- [ ] Mutation score gated; zero survivors in threshold and verdict logic.
- [ ] No unhandled exception escapes `core/`; no `NaN` can reach output.
- [ ] Read-only assurance across all engines, plus a passing zero-egress test.
- [ ] `make verify-full` green.
