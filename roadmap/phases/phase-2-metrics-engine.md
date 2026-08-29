# P2 — Metrics Engine

**Goal:** implement every metric in [`02-metrics-spec.md`](../02-metrics-spec.md), each one
proven correct against two independent references: a naive implementation, and a synthetic
dataset whose true value is known by construction.

This is the phase where correctness is either established or lost. A wrong metric is worse
than a missing metric, because a wrong metric gets trusted.

**Entry criteria:** P1 exit checklist complete.

**Exit gate**

```bash
pytest tests/oracle tests/property tests/unit -q && make verify
```

---

## P2-01 — Metric result types and verdict model

**Depends on:** P1-01 · **Size:** M · **Touches:** `vhecfsck/models/metrics.py`, `tests/unit/test_metric_models.py`

**Contract**
- `MetricState` enum: `OK`, `WARN`, `FAIL`, `UNAVAILABLE`, `DISABLED`, with an explicit
  severity ordering for aggregation.
- `Verdict` enum: `OK`, `WARN`, `FAIL`, `INCONCLUSIVE`.
- `EvidenceStrength` enum: `HIGH`, `MEDIUM`, `LOW`.
- `ThresholdSpec`: `warn`, `fail`, `direction` (`LOWER_IS_WORSE` / `HIGHER_IS_WORSE`), with
  validation that `warn` is less severe than `fail` for the given direction.
- `MetricResult` (frozen): `id`, `state`, `value: float | None`, `unit`, `thresholds`,
  `sampling: dict`, `detail: dict`, `evidence_strength`, `explanation`,
  `remediation_hint`, `unavailable_reason: str | None`.
- Constructor invariants: `state == UNAVAILABLE` requires `value is None` **and** a non-empty
  `unavailable_reason`; `state in {OK, WARN, FAIL}` requires `value is not None`. This is
  where [CORRECTION 1](../02-metrics-spec.md) becomes structurally impossible to violate —
  you cannot construct an unavailable metric that carries a number.

**Tests first**
- Every illegal combination raises at construction.
- Severity ordering: `OK < WARN < FAIL`; `max()` over a list yields the worst.
- `ThresholdSpec` rejects inverted thresholds for each direction.

**Acceptance criteria**
- [ ] Round-trips through JSON without loss.
- [ ] `mypy --strict` clean.

---

## P2-02 — Deterministic sampling

**Depends on:** P0-07 · **Size:** S · **Touches:** `vhecfsck/core/sampling.py`, `tests/unit/test_sampling.py`

**Contract**
- `derive_rng(root_seed, purpose: str) -> Generator` — a named sub-stream per purpose
  (`"canary_queries"`, `"hubness_sample"`, `"bootstrap"`), so adding a third consumer never
  shifts the samples the first two draw. Global RNG use is banned by lint rule.
- `sample_without_replacement(ids, n, rng)` — stable, sorted output for reproducible
  downstream ordering.
- `bootstrap_indices(n, resamples, rng)` — for the canary confidence interval.

**Tests first**
- Same `(root_seed, purpose)` → identical draws; different purposes → independent draws.
- Adding a new purpose does not change the output of existing purposes (regression-locked
  against a golden list).
- `n >= len(ids)` returns all IDs, sorted, without error.

**Acceptance criteria**
- [ ] No use of `np.random.seed` or the global RNG anywhere in the package.

---

## P2-03 — Naive reference implementations (oracle)

**Depends on:** P1-01 · **Size:** M · **Touches:** `tests/oracle/reference.py`, `tests/oracle/test_reference_selfcheck.py`

**Goal:** write the slow, obviously-correct version **before** the fast one. This is a
permanent test asset, not scaffolding.

**Contract**
- `naive_knn(corpus, queries, k, metric_space)` — full distance matrix, `argsort`, ties by
  ascending ID. Deliberately unoptimised and written for readability, because its only job
  is to be obviously right.
- `naive_recall(gt_ids, returned_ids, ...)` — direct set intersection, per query, in Python.
- `naive_nk(corpus, k)` — `O(S²)` neighbour counting with an explicit loop.
- `naive_cv(sizes)` — plain formula.
- Each has a docstring citing the section of [`02-metrics-spec.md`](../02-metrics-spec.md) it
  implements.

**Tests first (self-check)**
- `naive_knn` reproduces Fixture A from [`§2.6`](../02-metrics-spec.md) exactly.
- `naive_nk` reproduces Fixture B from [`§3.7`](../02-metrics-spec.md) exactly.
- `naive_cv` reproduces Fixture C from [`§5.4`](../02-metrics-spec.md) exactly.

**Acceptance criteria**
- [ ] Lives under `tests/`, never imported by production code (import-linter enforced).
- [ ] Handles all three metric spaces.
- [ ] No optimisation, ever. If it becomes too slow for a test, shrink the test input, do not
      speed up the oracle — an optimised oracle is no longer an independent check.

---

## P2-04 — Blocked BLAS ground truth

**Depends on:** P2-03 · **Size:** L · **Touches:** `vhecfsck/core/ground_truth.py`, `tests/oracle/test_ground_truth.py`, `tests/perf/test_ground_truth_perf.py`

**Goal:** exact k-NN at 1M × 768 within the memory budget, implementing
[`02-metrics-spec.md §2.3`](../02-metrics-spec.md) and
[ADR-0005](../adr/0005-ground-truth-precision-and-blocking.md).

**Contract**
- `exact_knn(corpus_iter, queries, k, metric_space, *, working_set_mb, on_progress) -> KnnResult`
  returning IDs, distances, and the `d_K` boundary per query.
- Streams corpus blocks; block size derived from `working_set_mb` and never from a hardcoded
  constant.
- One `sgemm` per block. `L2` uses the `‖a‖² - 2a·b + ‖b‖²` expansion with precomputed norms,
  and **must** clamp small negative results to zero before `sqrt` — floating-point
  cancellation produces negatives around `-1e-7` for near-identical vectors, which becomes
  `nan` and silently poisons a whole row of ground truth.
- Accumulation in `float32` minimum, never `float16`; `float16` input is upcast on read.
- Top-`k` merge across blocks via `argpartition` plus a bounded merge, ties by ascending ID.
- Progress callback for the CLI and the WebSocket stream; cancellable via a deadline
  (`max_seconds`), returning a `truncated` flag rather than a partial result presented as
  complete.
- `float64` cross-check helper used by tests on a small slice, verifying the `float32` path
  produces the same ordering.

**Tests first**
- Differential against `naive_knn` on 200 randomised cases across all three spaces, varying
  `n`, `d`, `k`, and block size: identical ID sets for tie-free inputs, distances equal
  within `1e-5` relative tolerance.
- **Block-size invariance:** results are identical for block sizes 1, 7, 999 and `n` — the
  single most valuable test in this ticket, because block-boundary bugs are the likeliest
  defect and the hardest to spot in aggregate.
- Duplicate vectors: ties resolve by ascending ID, deterministically.
- `k > n` handled per edge case 1.
- Near-identical vectors under `L2` never produce `nan` (the clamp test).
- Perf (nightly): 1M × 768, `Q=200`, `k=10` within the budget recorded in
  [`release-plan.md`](../release-plan.md), peak RSS under the declared ceiling.

**Acceptance criteria**
- [ ] Peak additional memory beyond the corpus is under `2 × working_set_mb`.
- [ ] Identical results single- and multi-threaded BLAS (or a documented tolerance if BLAS
      reduction order makes exact equality impossible — measure before assuming).

---

## P2-05 — Canary recall

**Depends on:** P2-04 · **Size:** M · **Touches:** `vhecfsck/core/canary.py`, `tests/oracle/test_canary.py`, `tests/property/test_canary_props.py`

**Contract**
- Implements [`02-metrics-spec.md §2`](../02-metrics-spec.md) in full: `recall_id`,
  `recall_dist` (tie-tolerant, `rtol = 1e-6`), bootstrap 95% interval, and every diagnostic
  in `detail`.
- True distances for returned IDs are **recomputed from corpus vectors**, never read from the
  engine's distance field.
- Query-set resolution per §2.4 including self-exclusion, with `evidence_strength` assigned
  from the source and sample size.
- Returns a `MetricResult`; guards map to `UNAVAILABLE` with a specific reason.

**Tests first**
- **Fixture A asserted exactly**: `recall_id == 0.5`, `recall_dist == 1.0`. This is the
  regression test for [CORRECTION 2](../02-metrics-spec.md) and must never be deleted.
- Exact-search adapter → recall exactly `1.0`.
- Every edge case in §2.5 has a named test, including short returns, duplicate returns,
  dead-ID returns, and mid-audit ID disappearance.
- Self-exclusion changes the result by approximately `1/k` when queries are corpus-drawn —
  asserted numerically, which is what proves the exclusion is actually happening.
- Property: recall ∈ `[0, 1]`; permuting corpus rows does not change recall; recall is
  monotonically non-decreasing in `nprobe` on the synthetic IVF adapter.
- Bootstrap interval contains the point estimate and is reproducible under a fixed seed.

**Acceptance criteria**
- [ ] `detail.returned_invalid` is non-zero for the `tombstoned` scenario — the direct
      evidence of path blocking.
- [ ] Threshold crossings match the spec table exactly at the boundaries (`0.85`, `0.70`
      tested from both sides).

---

## P2-06 — Hubness

**Depends on:** P2-04 · **Size:** L · **Touches:** `vhecfsck/core/hubness.py`, `tests/oracle/test_hubness.py`, `tests/property/test_hubness_props.py`

**Contract**
- Implements [`02-metrics-spec.md §3`](../02-metrics-spec.md) with the **corrected sampling
  regime**: an independent sample `S` of live IDs, all of them used as queries against the
  sample, self excluded ([ADR-0006](../adr/0006-hubness-sampling-regime.md)).
- Never materialises the `S × S` matrix; reuses the blocked strategy from P2-04.
- Emits `hub_share_top1pct` and `antihub_fraction` as two `MetricResult`s sharing one
  `sampling` block, plus the §3.5 diagnostics: `max_nk`, `p99_nk`, `median_nk`, bucketed
  histogram, MAD-based `hub_outlier_count`, capped `hub_ids` / `antihub_ids`,
  `duplicate_vector_pairs`, `norm_p99_ratio`.
- Asserts the internal invariant `sum(N_k) == S · k_hub` and raises `InternalError` if
  violated. A silent violation here means every hubness number in the report is wrong.
- Sets `thresholds_uncalibrated_for_sample_size` when `S` or `k_hub` differ from the
  calibration point.
- `--hubness-source engine` variant reusing the same counting code over engine results.

**Tests first**
- **Fixture B asserted exactly**: `N_k == [1, 2, 1, 0]`, `antihub_fraction == 0.25`,
  `hub_share_top1pct == 0.5` (guards disabled for the unit test).
- Differential against `naive_nk` on randomised inputs, all three metric spaces.
- Guards: `S < 1000` → `UNAVAILABLE`; `k_hub >= S` → `UNAVAILABLE`.
- Degenerate case: all vectors identical → `antihub_fraction == 0`, `hub_share == 0.01`.
- Property: both metrics ∈ `[0, 1]`; invariant under row permutation; invariant under global
  rotation; `inject_hubs` monotonically increases `hub_share`; `inject_antihubs`
  monotonically increases `antihub_fraction`.
- **Regression test for [CORRECTION 3](../02-metrics-spec.md)**: a healthy 50k-vector corpus
  audited with `Q = 200` canary queries must **not** report an anti-hub fraction near `1.0`.
  This test exists specifically to fail if anyone ever re-couples hubness sampling to the
  canary query set.

**Acceptance criteria**
- [ ] `S = 20_000`, `d = 768` completes in under 30 s on the reference machine.
- [ ] Peak memory for the hubness stage under 512 MB beyond the sample itself.

---

## P2-07 — Deletion fragmentation index

**Depends on:** P2-01 · **Size:** S · **Touches:** `vhecfsck/core/fragmentation.py`, `tests/unit/test_fragmentation.py`

**Contract**
- Implements [`02-metrics-spec.md §4`](../02-metrics-spec.md). Pure computation over an
  `IndexCounts` plus an optional per-fragment breakdown; all engine-specific derivation lives
  in adapters.
- Honours `exact` / `estimated` / `proxy` flags, capping `evidence_strength` accordingly.
- Handles the `entrypoint_tombstoned` escalation path (accepts the flag now, even though no
  adapter supplies it until P7).
- Reports the per-fragment distribution, not just the aggregate.

**Tests first**
- `apply_churn(0.2)` → DFI exactly `0.2`.
- `report_deleted_counts = False` → `UNAVAILABLE`, never `0.0`. **This is the highest-value
  test in the ticket** and directly encodes [CORRECTION 1](../02-metrics-spec.md).
- Every §4.4 edge case, including the `dead > total` clamp.
- `entrypoint_tombstoned = True` forces `FAIL` even at DFI `0.01`.
- Threshold boundaries `0.15` / `0.30` tested from both sides.

---

## P2-08 — Partition size CV

**Depends on:** P2-01 · **Size:** S · **Touches:** `vhecfsck/core/partitions.py`, `tests/unit/test_partitions.py`, `tests/property/test_partitions_props.py`

**Contract**
- Implements [`02-metrics-spec.md §5`](../02-metrics-spec.md); `ddof = 0` explicitly and
  documented at the call site.
- Companion diagnostics: `max_over_mean`, `p99_over_mean`, `gini`,
  `empty_partition_fraction`, `n_partitions`, `top_partitions`.
- Accepts `GraphStats` in-degree data through the same module for the post-MVP HNSW variant,
  but reports it as `UNAVAILABLE` until an adapter provides it.

**Tests first**
- **Fixture C asserted exactly**: `cv ≈ 1.6895464932727084`, `max_over_mean ≈ 3.9263803680981595`.
- `ddof=1` would give a different number — assert the population value specifically, so a
  future "cleanup" to `ddof=1` fails loudly.
- Every §5.3 edge case: non-IVF → `UNAVAILABLE(not_applicable)`, `n_partitions <= 1` →
  `UNAVAILABLE`, all-empty → `UNAVAILABLE(empty_index)`.
- Property: `cv >= 0`; uniform sizes → `cv == 0`; permutation-invariant; scale-invariant;
  monotonic under mass concentration.
- `skew_partitions(target_cv=1.5)` measures within 5% of 1.5.

---

## P2-09 — Verdict engine

**Depends on:** P2-01, P0-07 · **Size:** S · **Touches:** `vhecfsck/core/verdict.py`, `tests/unit/test_verdict.py`

**Contract**
- `evaluate(value, thresholds) -> MetricState` derived from `direction`, never per-metric
  branching.
- `aggregate(results, *, strict_unavailable) -> Verdict` implementing
  [`02-metrics-spec.md §6`](../02-metrics-spec.md), including the rule that a `LOW`-evidence
  metric contributes at most `WARN`.
- `verdict_to_exit_code(verdict) -> ExitCode`.

**Tests first**
- Exhaustive truth table over `{OK, WARN, FAIL, UNAVAILABLE, DISABLED}` combinations ×
  `strict_unavailable` ∈ `{True, False}`. Written as a table, not as prose-named tests, so
  coverage is visibly complete.
- A `FAIL`-valued metric with `LOW` evidence yields at most `WARN`.
- All-`DISABLED` yields `INCONCLUSIVE`, not `OK` — an audit that checked nothing did not pass.

**Acceptance criteria**
- [ ] 100% branch coverage on this module. It is small, and every branch is a production
      decision about whether to page someone.

---

## P2-10 — Audit pipeline orchestration

**Depends on:** P2-05, P2-06, P2-07, P2-08, P2-09 · **Size:** M · **Touches:** `vhecfsck/pipeline.py`, `tests/unit/test_pipeline.py`

**Contract**
- `run_audit(adapter, config, *, on_progress) -> Report` — the single entry point used by
  both the CLI and the server.
- Order of operations: validate inputs (§1.6) → read counts → resolve queries → ground truth
  → canary → hubness → DFI → partitions → aggregate verdict → assemble report.
- **Ground truth is computed once and shared** between canary and hubness where the sample
  overlaps. Computing it twice would double the most expensive stage.
- Per-stage timing, a stage-level deadline honouring `max_seconds`, and a memory ceiling
  check that degrades sampling rather than being OOM-killed.
- A failure in one metric never aborts the audit: that metric becomes `UNAVAILABLE` with the
  reason recorded, and the rest proceeds. A partial audit is useful; a crashed audit is not.
- Collects report-level warnings (`snapshot_inconsistent`, `thresholds_uncalibrated_*`, …).

**Tests first**
- Each P1-08 scenario produces its documented verdict and per-metric states.
- A metric raising an unexpected exception degrades to `UNAVAILABLE` and the audit still
  returns a report.
- `max_seconds` exceeded → `truncated` flags set, evidence downgraded, verdict still
  produced.
- Ground truth is computed exactly once (asserted with a call counter).

---

## P2-11 — Determinism harness

**Depends on:** P2-10 · **Size:** S · **Touches:** `tests/property/test_determinism.py`

**Goal:** protect invariant 4 from [`00-vision-and-scope.md §7`](../00-vision-and-scope.md).

**Contract**
- Run each scenario twice in one process and once in a fresh subprocess; assert the
  serialised reports are byte-identical after normalising the genuinely volatile fields
  (timestamps, durations, host info).
- Assert the volatile-field allowlist is itself frozen, so a future non-deterministic value
  cannot be waved through by adding it to the list without a deliberate change.

**Acceptance criteria**
- [ ] Passes in-process, cross-process, and with `PYTHONHASHSEED` varied.
- [ ] Fails if any code path uses the global RNG or unordered set iteration in a way that
      reaches the output.

---

## Phase exit checklist

- [ ] All five metrics implemented, each with a naive-oracle differential test and a
      known-true-value synthetic test.
- [ ] Fixtures A, B and C asserted exactly, with their spec sections cited in the tests.
- [ ] Corrections 1, 2 and 3 each have a dedicated regression test that fails if the
      correction is ever reverted.
- [ ] `UNAVAILABLE` can never carry a value — enforced at construction, not by convention.
- [ ] Determinism verified in-process and cross-process.
- [ ] Coverage ≥90% on `core/`, 100% branch coverage on `verdict.py`.
- [ ] `core/` imports nothing from `adapters/`, `server/`, `report/` or `cli`.
