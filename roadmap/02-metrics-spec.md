# 02 — Metrics Specification (normative)

This document is the authority on what every number means. Where it disagrees with any
other document, including the upstream architecture blueprint, **this document wins**. Any
implementation ticket that touches `vhecfsck/core/` must cite the section it implements.

Four defects in the source specification are corrected here. They are marked **[CORRECTION]**
inline so the deviation is never mistaken for a transcription error.

---

## 1. Common conventions

### 1.1 Metric spaces

| Space | Comparison | Handling |
| :--- | :--- | :--- |
| `COSINE` | higher similarity is better | L2-normalise corpus and queries once at ingest, then use dot products. Assert `abs(norm - 1) < 1e-4` after normalisation. |
| `L2` | lower distance is better | Squared L2 used internally; `sqrt` only applied when a distance is reported to a human. Ordering is identical, so the oracle compares squared values. |
| `DOT` (inner product) | higher is better | No normalisation. Vector magnitude is meaningful, which makes hub injection via large norms a real attack surface — see §3.6. |

The metric space is **read from the target index**, never assumed and never taken from a
CLI flag. If the adapter cannot determine it, the audit aborts with a usage error (exit `4`);
it does not guess. Measuring recall in the wrong space produces a plausible-looking number
that is entirely meaningless, which is worse than no number at all.

### 1.2 Determinism

Every sampling decision derives from a single root seed (`--seed`, default `1337`), recorded
in the report. Derived streams use `numpy.random.default_rng(seed).spawn()` or explicit
sub-seeds, never a global RNG. All ties — in distance, in `N_k` ranking, in top-`k`
selection — break by **ascending vector ID**. Two runs with the same seed against the same
immutable target must produce byte-identical reports, and there is a test that asserts
exactly that.

### 1.3 Metric result states

```text
OK           metric computed, within healthy thresholds
WARN         metric computed, crossed the warn threshold
FAIL          metric computed, crossed the fail threshold
UNAVAILABLE  metric could not be computed (missing capability, guard not met, error)
DISABLED     metric explicitly turned off in configuration
```

**[CORRECTION 1] `UNAVAILABLE` is never rendered as a healthy value.** The source
specification had no representation for "unknown", which means an engine unable to report
dead-tuple counts would have scored a perfect DFI of `0.0`. Unknown must look different
from good, in the JSON, in the terminal, and in Prometheus (where the metric is simply not
emitted, and a companion `vhecfsck_metric_unavailable{metric="…"} 1` series is). See
[ADR-0004](adr/0004-metric-result-states-and-exit-codes.md).

### 1.4 Evidence strength

Every metric carries an honest self-assessment, because a recall figure from 200
corpus-drawn queries and one from 50,000 production queries are not the same claim.

| Value | Meaning |
| :--- | :--- |
| `high` | Sample size meets the calibrated target and the input is production-representative (e.g. a real query log). |
| `medium` | Sample meets the guard minimum but is synthetic, corpus-drawn, or below the calibrated target. |
| `low` | Sample barely clears the guard. Reported, and downgraded to `WARN` at most — a `low`-evidence metric may never produce a `FAIL` verdict on its own. |

### 1.5 Threshold direction

`lower_is_worse` (canary recall) or `higher_is_worse` (DFI, hub share, anti-hub fraction,
partition CV). The comparison operator is derived from the direction, never hardcoded per
metric, so a mis-signed threshold is impossible.

### 1.6 Global input validation

Applied before any metric runs. All are hard errors (exit `4`), not warnings:

- `NaN` or `Inf` in any vector. The report lists up to 20 offending IDs.
- Dimension mismatch between queries and corpus.
- Zero-norm vectors under `COSINE`, where cosine is undefined. These are excluded from
  ground truth, counted in `counts.degenerate`, and surfaced as a report warning; the audit
  continues.
- Fewer than 2 live vectors.

---

## 2. M1 — Canary Recall

**ID:** `canary_recall` · **Unit:** ratio · **Direction:** `lower_is_worse`
**Thresholds:** `WARN < 0.85`, `FAIL < 0.70`
**Implements:** `core/ground_truth.py`, `core/canary.py`

### 2.1 The question

Does the index still return the answers that brute force says are correct? This is the
headline metric. Everything else explains *why* this one moved.

### 2.2 Definition

Given a query set `Q`, neighbour count `K`, the live corpus `C`, and the engine's own
approximate search:

```text
GT_K(q)    = the exact K nearest live vectors to q, brute force, ties broken by ascending id
R_K(q)     = ids returned by adapter.search(q, K, params), deduplicated
d_K(q)     = the true distance from q to the K-th element of GT_K(q)
n_eff(q)   = min(K, |live vectors eligible for q|)

recall_id(q)   = |GT_K(q) ∩ R_K(q)| / n_eff(q)
recall_dist(q) = |{ i ∈ R_K(q) : true_dist(q, i) ≤ d_K(q) · (1 + rtol) }| / n_eff(q)
```

with `rtol = 1e-6`, and `≥ d_K·(1 - rtol)` for similarity spaces. The reported metric is the
mean over `Q` of each, and **`recall_dist` is the value that gates the verdict**.

**[CORRECTION 2] Recall must be tie-tolerant.** The source specification defines recall as
an ID set intersection. When the `K`-th and `K+1`-th true neighbours are equidistant — which
is routine with duplicate or near-duplicate documents, and universal in quantised indexes —
the engine returns an answer that is *exactly as correct* as ours and gets marked wrong.
Both values are reported so users can see the gap; only the tie-tolerant one is gated. See
[ADR-0007](adr/0007-tie-tolerant-recall.md).

**`recall_dist` is not ours — it is the published ANN-Benchmarks definition, and we should
say so.** Correcting the source specification was necessary, but the corrected form is the
standard one used by the reference benchmark of the field:

> Aumüller, Bernhardsson & Faithfull, *ANN-Benchmarks: A benchmarking tool for approximate
> nearest neighbor algorithms*, **Information Systems** 87 (2019),
> [doi:10.1016/j.is.2019.02.006](https://doi.org/10.1016/j.is.2019.02.006), §2.1:
>
> ```text
> recall_ε(π, π*) = |{ p ∈ π : dist(p, q) ≤ (1 + ε) · dist(p*_K, q) }| / K
> ```

That is the formula above with `ε = rtol`. Citing it makes the metric checkable against
external work instead of asking the reader to trust a house correction.

Two further points that are easy to get wrong:

- `true_dist` is **recomputed by us from the corpus vectors**, never taken from the
  engine's returned distance field. Under product quantisation the engine's distances are
  approximations of the very thing we are auditing.
- An ID returned by the engine that is dead, unknown, or out of range counts as a miss and
  is separately tallied in `detail.returned_invalid`. That count is the smoking gun for
  tombstone path blocking, and it is often more diagnostic than the recall number itself.

### 2.3 Algorithm

1. Resolve the query set (§2.4) into `Q × D`, normalised if the space is cosine.
2. Compute exact ground truth by blocked BLAS:
   - Stream live corpus blocks of `B` rows, `B` chosen so `B × D × 4` bytes plus
     `Q × B × 4` bytes fits the working-set budget (default ~256 MB).
   - Per block: one `sgemm` (`DOT`/`COSINE`) or one `sgemm` plus norm correction (`L2`).
   - Reduce with `argpartition(k)`, then merge each block's top-`k` into a running
     top-`k` with global IDs, tie-broken by ascending ID.
   - Accumulate in `float32` minimum. See [ADR-0005](adr/0005-ground-truth-precision-and-blocking.md).
3. Call `adapter.search(queries, K, params)` once, batched.
4. Compute both recall variants per query; aggregate.
5. Compute a 95% interval by **percentile bootstrap resampling over queries** (default
   1,000 resamples, seeded; Efron, *Bootstrap Methods: Another Look at the Jackknife*,
   **Annals of Statistics** 7(1):1–26, 1979,
   [doi:10.1214/aos/1176344552](https://doi.org/10.1214/aos/1176344552)). This is
   resampling of observed data, not a distributional assumption, so it stays inside the
   "empirical only" constraint ([ADR-0003](adr/0003-empirical-metrics-only.md)).

   **Declared deviation:** the interval is widened, if necessary, to contain the point
   estimate (`ci_lo = min(ci_lo, mean)`, `ci_hi = max(ci_hi, mean)`; see
   `vhecfsck/core/canary.py`). A percentile bootstrap can exclude the mean at very small
   `Q`, and an interval that does not contain the number it qualifies is worse than useless
   to a reader. This makes the interval conservative and no longer a pure percentile
   bootstrap — which is why it is stated here rather than left in a code comment.

### 2.4 Query set resolution

| Source | Flag | Evidence | Notes |
| :--- | :--- | :--- | :--- |
| Production query log | `--queries file.npy \| .parquet` | `high` | Preferred. The only source that reflects real traffic. |
| Random live corpus vectors | default | `medium` | **Self-matches excluded by default** (`--include-self` to disable). Without exclusion, every query is its own nearest neighbour at distance 0 and recall is inflated by roughly `1/K`. Corpus-drawn queries also sample an easier distribution than real traffic — recall measured this way is an optimistic bound. |
| Synthetic generator | `demo` command | `medium` | Deterministic, used for the demo and tests. |

Defaults: `Q = 200`, `K = 10`. Guards: `Q < 30` → `low` evidence; `Q < 5` → `UNAVAILABLE`.

### 2.5 Edge cases (all require a test)

| # | Case | Required behaviour |
| :--- | :--- | :--- |
| 1 | `n_live < K` | Normalise by `n_live`. `n_live == 0` → `UNAVAILABLE`. |
| 2 | Engine returns fewer than `K` results | Missing slots count as misses; record `detail.short_returns`. |
| 3 | Engine returns duplicate IDs | Deduplicate before scoring; record `detail.duplicate_returns`. |
| 4 | Engine returns dead / unknown IDs | Count as miss; record `detail.returned_invalid`. |
| 5 | Distance ties at the `K` boundary | Handled by `recall_dist`; `detail.boundary_ties` records how many queries were affected. |
| 6 | Exact duplicate vectors in the corpus | Legal. Deterministic ID tie-break. Reported in `counts.duplicate_vectors`. |
| 7 | Index mutated mid-audit (IDs vanish) | Tolerate, count, emit report warning `snapshot_inconsistent`; do not crash and do not silently drop. |
| 8 | Query vector present in corpus with a different ID | Not self-matching; a legitimate distance-0 neighbour. Do not exclude. |
| 9 | Search params omitted | Adapter reports engine defaults; the effective params are echoed into the report. A recall number without `ef_search`/`nprobe` is not interpretable. |
| 10 | Time budget exceeded | Ground truth degrades to a smaller `Q`, evidence drops, `detail.truncated = true`. Never a partial silent result. |

### 2.6 Oracle and test vectors

The blocked implementation is differentially tested against a naive
`for q: argsort(all distances)` reference on randomised inputs (`tests/oracle/`): identical
ID sets for tie-free inputs, and identical distances within `1e-5` relative tolerance.

**Fixture A — hand-verified, 2D, `L2`, `K = 2`.** Values below were computed and confirmed
numerically; assert them exactly.

```python
corpus = [[0,0], [1,0], [0,1], [10,0], [10,1], [0,10]]   # ids 0..5
query  = [0.1, 0.1]
# true distances: [0.141421, 0.905538, 0.905538, 9.900505, 9.940825, 9.900505]
# ids 1 and 2 are exactly equidistant -> tie-break by ascending id
# GT_2 = [0, 1],  d_K = 0.905538

engine_returns = [0, 2]      # a perfectly reasonable answer
assert recall_id   == 0.5    # punished for a tie it did not lose
assert recall_dist == 1.0    # correct
```

This fixture is the regression test for `CORRECTION 2` and must never be deleted.

### 2.7 Report fields

```jsonc
{"id": "canary_recall", "state": "FAIL", "value": 0.61, "unit": "ratio",
 "thresholds": {"warn": 0.85, "fail": 0.70, "direction": "lower_is_worse"},
 "sampling": {"queries": 200, "k": 10, "query_source": "corpus",
              "self_excluded": true, "search_params": {"nprobe": 20, "refine_factor": null}},
 "detail": {"recall_id": 0.58, "recall_dist": 0.61, "ci95": [0.57, 0.65],
            "returned_invalid": 412, "short_returns": 7, "duplicate_returns": 0,
            "boundary_ties": 3, "truncated": false},
 "evidence_strength": "medium"}
```

---

## 3. M2/M3 — Hubness: Top-1% Hub Share and Anti-Hub Fraction

**IDs:** `hub_share_top1pct`, `antihub_fraction` · **Unit:** ratio · **Direction:** `higher_is_worse`
**Thresholds:** hub share `WARN > 0.20`, `FAIL > 0.35` · anti-hub `WARN > 0.25`, `FAIL > 0.40`
**Implements:** `core/hubness.py`

### 3.1 [CORRECTION 3] The sampling regime — read this before implementing

The source specification computes both metrics from the same `Q = 200` probe queries used
for canary recall. **That definition cannot pass.** With `K = 10`, at most `Q × K = 2,000`
distinct vectors can ever be returned, so on a 1M-vector corpus the anti-hub fraction is at
least `1 - 2000/1000000 = 0.998` and the check fails unconditionally, on a perfectly healthy
index. The published thresholds (warn `0.25`, fail `0.40`) are recognisable values from the
classical hubness literature, where `N_k` is computed with **every point in the dataset
acting as a query**. The definition and the thresholds come from two different regimes.

The correction: hubness metrics get their own sampling regime, fully decoupled from canary
recall.

```text
S      = a deterministic random sample of live vector ids   (default 20_000)
k_hub  = neighbour count for hubness                        (default 10)

For each x in S:  find its exact k_hub nearest neighbours within S, excluding x itself.
N_k(x)          = number of times x appears in the neighbour lists of the other S-1 points.
total_slots     = |S| · k_hub                     (and sum(N_k) == total_slots, an invariant)
```

```text
hub_share_top1pct = sum of the ceil(0.01·|S|) largest N_k values / total_slots
antihub_fraction  = |{ x ∈ S : N_k(x) == 0 }| / |S|
```

See [ADR-0006](adr/0006-hubness-sampling-regime.md).

### 3.2 Comparability constraint

Measured hubness depends on `|S|`: with fewer competitors, each point has fewer chances to
be someone's neighbour, so both metrics shift as `S` changes. Therefore:

- `|S|` and `k_hub` are recorded in the report, always.
- Cross-run comparison is only valid at identical `|S|` and `k_hub`. Baseline mode refuses
  to compare across different values and emits `not_comparable`.
- Default thresholds are calibrated at `|S| = 20_000, k_hub = 10` ([P8](archive/phases/phase-8-calibration-and-hardening.md)).
  Running with different values sets the report warning
  `thresholds_uncalibrated_for_sample_size`. The number is still computed and shown; it is
  just not gated against defaults that do not apply to it.

This is the honest position. Pretending a metric is scale-free when it is not is how a
checker earns a reputation for false alarms and gets removed from the pipeline.

### 3.3 Source: intrinsic vs effective

| Source | Flag | Measures |
| :--- | :--- | :--- |
| Ground truth (default) | `--hubness-source truth` | **Intrinsic** hubness of the embedding space. Engine-independent, stable across index rebuilds. Answers "is my embedding model producing cannibals?" |
| Engine search | `--hubness-source engine` | **Effective** hubness as users experience it, including index approximation error. Answers "what is actually being served?" |

Default is `truth`, because it is reproducible and isolates the embedding space from the
index. Both are cheap once ground truth exists, so the engine variant may be emitted
alongside as `detail.effective_*`.

### 3.4 Cost

`S = 20,000`, `D = 768`: `S²/2` pairs ≈ 2×10⁸ dot products ≈ 3×10¹¹ FLOP — a few seconds on
a modern CPU with BLAS. The `S × S` matrix is **never materialised** (1.6 GB in `float32`);
the same blocked row-strip reduction as ground truth is used, with a per-strip working set
of roughly 160 MB at `S_b = 2,000`.

### 3.5 Additional diagnostics (reported, not gated)

- `max_nk`, `p99_nk`, `median_nk`, and the full `N_k` histogram (bucketed for transport).
- `hub_outlier_count`: vectors with `N_k > median(N_k) + 5 · MAD(N_k)`, where
  `MAD = median(|N_k - median(N_k)|)`. MAD is used instead of standard deviation precisely
  because the distribution is expected to be skewed. The constant `5` is a documented
  convention, not a derived value, and is configurable.
- `hub_ids` / `antihub_ids`: the top and bottom offenders, capped at 1,000 IDs each, feeding
  the 3D visualizer's red and blue point classes.
- `duplicate_vector_pairs`: exact duplicates create mutual-neighbour artefacts where one
  copy absorbs the other's `N_k` arbitrarily. Deterministic tie-breaking makes this
  reproducible; the count makes it visible.

### 3.6 Edge cases (all require a test)

| # | Case | Required behaviour |
| :--- | :--- | :--- |
| 1 | `|S| < 1,000` | `UNAVAILABLE`. Top 1% would be fewer than 10 vectors and the metric is noise. |
| 2 | `k_hub ≥ |S|` | `UNAVAILABLE`. |
| 3 | `|S|` differs from the calibration point | Compute, report, set `thresholds_uncalibrated_for_sample_size`. |
| 4 | Live corpus smaller than requested `S` | Use the whole corpus, set `S = n_live`, apply guard 1. |
| 5 | Large-norm vectors under `DOT` | A high-magnitude vector is a hub by construction in inner-product space. Do not "fix" it — report `detail.norm_p99_ratio` so the user can see whether hubness is a magnitude artefact. |
| 6 | All vectors identical | Every `N_k` equal, `antihub_fraction == 0`, `hub_share == 0.01`. Degenerate but well-defined; assert it. |
| 7 | `sum(N_k) != |S| · k_hub` | Internal invariant violation. Raise; never report a wrong number. |

### 3.7 Oracle and test vectors

**Fixture B — hand-verified, 1D, `k_hub = 1`, `S = 4`** (guards disabled for the unit test):

```python
points = [[0.0], [1.0], [2.0], [10.0]]      # ids 0..3
# 1-NN excluding self, ties by ascending id: [1, 0, 1, 2]
#   id0 -> id1 ; id1 -> id0 (tie with id2 at distance 1, id0 wins) ; id2 -> id1 ; id3 -> id2
assert N_k == [1, 2, 1, 0]
assert sum(N_k) == 4                        # == S * k_hub, invariant
assert antihub_fraction  == 0.25            # id3 is never anyone's neighbour
assert hub_share_top1pct == 0.5             # ceil(0.01*4) == 1 vector, id1, with 2 of 4 slots
```

Property tests (`tests/property/`): both metrics in `[0, 1]`; invariance under row
permutation; invariance under global rotation and (for cosine) under positive scaling;
`sum(N_k)` invariant; injecting a synthetic hub monotonically increases `hub_share`;
injecting distant outliers monotonically increases `antihub_fraction`.

---

## 4. M4 — Deletion Fragmentation Index (DFI)

**ID:** `dfi` · **Unit:** ratio · **Direction:** `higher_is_worse`
**Thresholds:** `WARN > 0.15`, `FAIL > 0.30`
**Implements:** `core/fragmentation.py` (adapters supply the raw counts)

### 4.1 Definition

```text
dfi = dead / (live + dead)
```

where `dead` counts entities the search may still traverse but will never return
(tombstones, dead tuples, deletion-file rows), and `live + dead` is the navigable
population — not the logical row count.

### 4.2 Per-engine derivation, and where it gets subtle

| Engine | Source | Exactness |
| :--- | :--- | :--- |
| **Lance / LanceDB** | Per-fragment `physical_rows` vs `num_rows`; the difference is the deletion-file population. | Exact |
| **pgvector** | `pg_stat_user_tables.n_dead_tup` vs `n_live_tup`; `pgstattuple` when the extension and privileges are present. | **Proxy.** These are table-level statistics, refreshed by the stats collector, and not an index-level tombstone count. Flag `proxy: true` and `estimated: true`. |
| **Qdrant** | Per-segment `num_deleted_vectors` / `num_vectors` from segment telemetry. | Exact where telemetry is exposed. |
| **Qdrant, naive fallback** | `points_count` vs `indexed_vectors_count`. | **Do not use as DFI.** `indexed_vectors_count` also excludes vectors in segments below the indexing threshold, so this ratio conflates "deleted" with "not yet indexed" — it would report fragmentation on a perfectly clean, freshly loaded collection. If segment telemetry is unavailable, DFI is `UNAVAILABLE`. |
| **Synthetic** | Exact by construction; the generator knows what it deleted. | Exact |

The Qdrant row is the reason `Capabilities` exists. An adapter that cannot get the right
number must say so rather than substitute a number that is merely available.

### 4.3 Companion sub-check: entry-point health (post-MVP, [P7](archive/phases/phase-7-qdrant-and-pgvector-adapters.md))

For HNSW indexes, whether the graph entry point is itself tombstoned is a boolean far more
actionable than any ratio — it is the mechanism behind
[`weaviate#11951`](https://github.com/weaviate/weaviate/issues/11951). Reported as
`detail.entrypoint_tombstoned` and, when true, escalates DFI to `FAIL` regardless of the
ratio. Requires graph-level introspection; `UNAVAILABLE` until an adapter can provide it.

### 4.4 Edge cases

| # | Case | Required behaviour |
| :--- | :--- | :--- |
| 1 | `live + dead == 0` | `UNAVAILABLE`. |
| 2 | Engine cannot report dead counts | `UNAVAILABLE`. Never `0.0`. |
| 3 | Counts are statistical estimates | Compute, set `estimated: true`, cap evidence at `medium`. |
| 4 | Counts drift during the audit | Read once, at a recorded timestamp; report the timestamp. |
| 5 | Multiple fragments/segments | Sum, and report the per-fragment distribution — one pathological fragment out of a hundred is invisible in the aggregate. |
| 6 | `dead > live + dead` from an inconsistent engine read | Clamp to `1.0`, emit warning `inconsistent_counts`. |

---

## 5. M5 — Partition Size CV (IVF)

**ID:** `partition_size_cv` · **Unit:** coefficient of variation · **Direction:** `higher_is_worse`
**Thresholds:** `WARN > 1.20`, `FAIL > 2.00`
**Implements:** `core/partitions.py`

### 5.1 Definition

```text
sizes = row count per IVF partition, including empty partitions
cv    = population_std(sizes) / mean(sizes)          # ddof = 0, explicitly
```

`ddof = 0` is normative. Partitions are the entire population, not a sample of one, and the
choice changes the number enough to matter at low `K`.

### 5.2 Companion diagnostics (reported, not gated)

CV summarises the whole distribution, but p99 query latency is driven by the *worst* cell a
query has to scan. These are frequently more actionable than CV itself:

- `max_over_mean` — the largest cell relative to the mean. The direct latency multiplier.
- `p99_over_mean`, `gini`, `empty_partition_fraction`, `n_partitions`.
- `top_partitions` — the ten largest cells with their sizes, for the visualizer.

### 5.3 Edge cases

| # | Case | Required behaviour |
| :--- | :--- | :--- |
| 1 | Not an IVF index (HNSW, flat) | `UNAVAILABLE` with reason `not_applicable`, not a failure. |
| 2 | `n_partitions <= 1` | `UNAVAILABLE`. CV is trivially 0 and meaningless. |
| 3 | `n_partitions < 8` | Compute, evidence `low`. |
| 4 | `mean == 0` (all partitions empty) | `UNAVAILABLE`, warning `empty_index`. |
| 5 | Deleted rows countable per partition | Prefer live counts; otherwise use physical counts and set `includes_deleted: true`. Mixing the two across partitions is forbidden. |
| 6 | Multi-index or multi-column table | One metric instance per index, keyed by index name. |

### 5.4 Oracle and test vectors

**Fixture C — hand-verified.** One pathological cell among three healthy ones, the
`lance#4164` shape in miniature:

```python
sizes = [500, 500, 500, 80000]
# mean = 20375.0 ; population std = 34424.509800431435
assert cv            == pytest.approx(1.6895464932727084)   # WARN: > 1.20, < 2.00
assert max_over_mean == pytest.approx(3.9263803680981595)
```

Assert against the closed-form computation, not against these printed digits, and use the
digits as the regression guard.

Property tests: `cv >= 0`; `cv == 0` for perfectly uniform sizes; invariance under
permutation of partitions; invariance under uniform scaling of all sizes (CV is
scale-free); monotonic increase as mass is concentrated into one cell.

---

## 6. Verdict aggregation

```text
verdict = worst state among all ENABLED metrics, where
          OK < WARN < FAIL

any UNAVAILABLE present            → verdict is at least INCONCLUSIVE
--strict-unavailable               → UNAVAILABLE is treated as FAIL
a low-evidence metric              → contributes at most WARN, never FAIL
DISABLED metrics                   → recorded in the report, excluded from the verdict
```

Exit codes, per [ADR-0004](adr/0004-metric-result-states-and-exit-codes.md):

| Code | Meaning |
| :--- | :--- |
| `0` | `OK` |
| `1` | `WARN` |
| `2` | `FAIL` |
| `3` | `INCONCLUSIVE` — audit ran, verdict could not be established |
| `4` | Usage / configuration / connection error |
| `70` | Internal error (unhandled exception; stack trace, bug report requested) |

`3` exists so that a CI pipeline can distinguish "your index is broken" from "the checker
could not tell". Collapsing those two into `2` trains users to ignore the tool.

---

## 7. Metrics deliberately deferred

Listed so nobody re-derives them mid-phase, and so the report schema can accommodate them
without a major version bump.

| Metric | Value | Blocked on |
| :--- | :--- | :--- |
| HNSW in-degree distribution / unreachable-node fraction | Directly quantifies path blocking rather than inferring it from tombstone ratios | Graph-level adapter introspection ([P7](archive/phases/phase-7-qdrant-and-pgvector-adapters.md)) |
| Centroid drift | Distance from stored centroids to recomputed k-means centroids over current data | Centroid extraction per engine |
| Recall-vs-`nprobe`/`ef_search` curve | Turns a pass/fail into a tuning recommendation | Multiple search sweeps; runtime cost |
| Per-tenant recall breakdown | The exact shape of [`qdrant#7147`](https://github.com/qdrant/qdrant/issues/7147) | Filtered-search support in the adapter protocol |
| Quantisation error (PQ/SQ reconstruction) | Separates quantisation loss from graph/partition damage | Codebook access |
| Temporal drift / trend | Turns a point-in-time check into an early-warning signal | Baseline persistence ([P8](archive/phases/phase-8-calibration-and-hardening.md)) |
