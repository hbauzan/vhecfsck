# ADR-0014 — Synthetic adapter before any real engine

**Status:** Accepted
**Affects:** P1, P2, P3, P4

## Context

The tool needs something to audit. The obvious starting point is the primary target engine
(LanceDB), which would give real data and real credibility from the first week.

The problem is diagnostic. If a metric implemented against LanceDB reports a hub share of 0.31,
there is no way to know whether that is correct. There are two candidate explanations for any
unexpected value — the metric is wrong, or the adapter is wrong — and no way to distinguish them.
Every bug in the first phase would be a two-suspect investigation, and worse, a metric that is
subtly wrong in a plausible-looking way would pass unnoticed, because there is nothing to compare
it against.

There is a second problem specific to a synthetic corpus that *does* answer correctly: if the
first adapter performs exact search, canary recall is a constant `1.0`, so the `WARN` and `FAIL`
code paths are untestable, the exit-code contract is unverifiable, and there is no demo. The
tempting fix — perturbing results with random noise to simulate degradation — would be actively
harmful: it would let us claim detection of a failure mode we never actually simulated, and the
demo would be a dramatisation rather than a reproduction.

## Decision

**The first adapter is an in-memory NumPy `SyntheticAdapter`, and it implements a mechanically
faithful approximate search.**

Three search modes:

1. **`exact`** — brute force. Recall is `1.0` by construction. This is the sanity baseline: if it
   ever drops below `1.0`, the ground-truth implementation is wrong, not the adapter. That single
   assertion validates the measurement apparatus itself.
2. **`ivf`** — seeded k-means centroids fitted once at "build" time, `nprobe` cells scanned per
   query. Appending vectors without refitting reproduces centroid drift and partition imbalance
   through the same mechanism as `lance#4164`.
3. **`ivf_tombstoned`** — as `ivf`, plus the critical ordering: gather the top `ef_budget`
   candidates by distance, **then** drop tombstoned IDs, **then** return the top `k` of what
   survives. This is exactly the pgvector/Weaviate/Qdrant path-blocking mechanism, and it is what
   makes a query legitimately return fewer than `k` results, or none at all.

Supporting decisions:

- **Pathologies are injected by operators that record the true induced value**
  (`GroundTruthAnnotation`), so every metric can be asserted against a known correct answer rather
  than merely against itself.
- **No degradation is ever simulated by random result corruption.** Every observed failure traces
  to a modelled mechanism.
- **The adapter may not import from `core/`.** Its k-means is a private implementation detail, not
  shared with the metric that measures its partitions — sharing code between the thing measured and
  the measuring instrument would make the test circular.
- **`report_graph_stats` is `False`**, because there is no graph. This exercises the `UNAVAILABLE`
  path from the first phase, rather than discovering it in P7.
- The synthetic adapter is **permanent**, not scaffolding. It powers `uvx vhecfsck demo` (no
  database required, which is the entire first-impression strategy), the fast test suite, and the
  cross-engine consistency check in `P7-07`.

## Consequences

**Buys:**
- Single-suspect debugging for the whole metrics phase.
- Every metric validated against an analytically known value before meeting a real engine.
- A demo that requires no database, no credentials and no dataset — the property that makes
  `uvx vhecfsck demo` viable as a hero command.
- Fast tests: the entire metric suite runs with no I/O, no containers and no network.
- A reproduction of the core failure mode in a unit test, which is a genuinely strong artifact for
  a reliability tool.

**Costs:**
- A real engine is not touched until P5, so the first evidence that the protocol generalises
  arrives late. Accepted: the protocol is designed in P1 with all three target engines in mind,
  and P5's explicit success criterion is that it needed no breaking change.
- The synthetic IVF implementation is real code that must be written and tested, and it is not
  shipped functionality in the usual sense. Justified by its permanent role in the demo and the
  test suite.
- Synthetic corpora are geometrically simpler than real embeddings, so a metric could be correct
  on synthetic data and surprising on real data. Mitigated by the reference-dataset calibration in
  `P8-01`, which is where real-world geometry enters.

## Alternatives considered

- **LanceDB first.** Rejected: two-suspect debugging for every metric bug, and no way to validate a
  metric against a known-true value.
- **A synthetic adapter with exact search only.** Rejected: recall is constant `1.0`, so `WARN`
  and `FAIL` paths, the exit-code contract, and the demo are all untestable.
- **A synthetic adapter that perturbs results with random noise.** Rejected as actively
  misleading, per the analysis above. This is the shortcut most likely to be proposed later by
  someone who has not read this ADR.
- **Recorded fixtures captured from a real engine.** Rejected: fixtures cannot be parameterised, so
  a controlled sweep of delete fraction or `nprobe` is impossible, and the true metric value is
  unknown for a recorded snapshot.

## Revisit if

Never for the ordering — P1 is complete. The synthetic adapter's fidelity may be extended (a
simplified HNSW mode would let the graph-level metrics be validated the same way, which is the
natural extension when `P7-06` establishes what real graph statistics are obtainable).
