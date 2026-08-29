# ADR-0007 — Gate on distance-thresholded recall

**Status:** Accepted
**Affects:** P2
**Corrects:** source specification defects 3 and 4

## Context

The source specification defines canary recall as the fraction of true neighbour **IDs**
recovered by the engine. That is the standard definition, and it is subtly wrong as a gating
metric.

Consider a corpus containing two vectors exactly equidistant from a query, at positions 10 and
11 in the true ranking, with `K = 10`. Ground truth must pick one — ours picks the lower ID.
The engine picks the other. Both answers are equally correct in every sense a user cares about;
the returned vector is exactly as close as the one we expected. Under ID-set recall the engine
loses 10% of its score for being right.

This is not a corner case. Near-duplicate documents are ubiquitous in real corpora (boilerplate,
templated content, re-uploaded files), and quantised indexes (PQ, SQ) collapse distinct vectors
onto identical codes by design, manufacturing ties in bulk. A tool that penalises engines for
ties will report degradation that is not there, and false alarms are how a checker gets removed
from a pipeline.

A second, independent problem sits in the same metric. If the query set is drawn from the corpus
— which is the default, since most users have no query log to hand — then each query is present
in the index and is its own nearest neighbour at distance 0. Every engine gets one free correct
answer, inflating recall by roughly `1/K`. A genuine recall of 0.85 reads as 0.865, and the
inflation is largest exactly where thresholds sit.

## Decision

**Compute and report two variants; gate on the tie-tolerant one.**

```text
recall_id(q)   = |GT_K(q) ∩ R_K(q)| / n_eff(q)

d_K(q)         = true distance from q to the K-th ground-truth neighbour
recall_dist(q) = |{ i ∈ R_K(q) : true_dist(q, i) ≤ d_K(q) · (1 + rtol) }| / n_eff(q)
```

with `rtol = 1e-6` (reversed for similarity spaces). `recall_dist` is the value compared against
thresholds; `recall_id` is reported alongside so users can see the gap, and a large divergence
between them is itself a useful diagnostic — it means the corpus is full of ties, which is worth
knowing.

Two supporting rules that make this correct rather than merely lenient:

- **True distances are recomputed by us from corpus vectors**, never read from the engine's
  reported distance field. Under product quantisation the engine's distances are approximations
  of the exact thing being audited; trusting them would let a quantisation error hide inside the
  metric.
- **Returned IDs that are dead, unknown or out of range count as misses**, and are separately
  tallied in `detail.returned_invalid`. Tie tolerance must not become tolerance for the engine
  returning garbage — and that counter turns out to be the single most diagnostic field in the
  report for tombstone path blocking.

**Self-matches are excluded by default** when queries are drawn from the corpus, with
`--include-self` to disable. Corpus-drawn query sets are additionally labelled
`evidence_strength: medium`, because they sample an easier distribution than production traffic:
every query is guaranteed to have a very close neighbour, which real queries are not. Recall
measured this way is an optimistic bound, and the report says so.

## Consequences

**Buys:** no false alarms from ties, so the metric survives contact with quantised indexes and
duplicate-heavy corpora. No systematic inflation from self-matching. And the `recall_id` /
`recall_dist` gap becomes a free signal about corpus duplication.

**Costs:**
- Two numbers to explain instead of one. Mitigated by gating on one and documenting why.
- `recall_dist` can slightly *overstate* recall in a pathological case: if the engine returns a
  vector that happens to sit at exactly `d_K` but is not in the true top-`K`, it counts as a hit.
  That is the intended behaviour — the returned vector is genuinely as close as the one expected
  — but it means `recall_dist ≥ recall_id` always, and the metric is deliberately generous to
  the engine at the boundary. Being generous at the boundary is the right bias for a gate that
  pages people.
- `rtol` is a magic constant. It is documented, tested at the boundary from both sides, and small
  enough to admit only genuine floating-point ties.

## Alternatives considered

- **ID-set recall only.** Rejected: false alarms on ties, as analysed above.
- **Distance-based recall only.** Rejected: `recall_id` is the number people know and expect, and
  publishing only a non-standard variant would invite the suspicion that we chose the definition
  that flatters. Publishing both, and being explicit about which gates, is more defensible.
- **Excluding tied boundary groups from scoring entirely.** Rejected: changes the denominator per
  query in a way that is hard to explain and makes cross-run comparison awkward.
- **Trusting the engine's reported distances.** Rejected: cannot detect quantisation error, which
  is one of the things worth detecting.

## Revisit if

Calibration in `P8-01` shows `recall_dist` masking real degradation on some index type — in
which case report the gap explicitly as a gated metric of its own rather than switching the
gating variable.
