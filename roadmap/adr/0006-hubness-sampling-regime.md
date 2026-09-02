# ADR-0006 — Hubness metrics use a self-queried subsample

**Status:** Accepted; **the threshold rationale below is superseded by ADR-0011 / P8-02**
**Affects:** P2, P8
**Corrects:** source specification defect 1 — the most serious defect found in review

> **Correction (MI-03).** The sampling-regime decision — the actual subject of this ADR —
> stands unchanged. Its *justification for keeping the 0.25 / 0.40 thresholds* does not.
> This ADR claimed those values were "recognisable values from the hubness literature";
> that attribution is wrong and is struck below. P8-02 subsequently measured that healthy
> isotropic Gaussians exceed the static thresholds from $d = 128$ upward and replaced them
> with per-dimension profiles ([ADR-0011](0011-thresholds-and-baseline-mode.md),
> [`docs/calibration/thresholds.md`](../../docs/calibration/thresholds.md)). The thresholds
> in force today are empirically calibrated, not inherited.

## Context

The source specification defines both hubness metrics over the canary probe query set:

> **Top-1% Hub Share** — Histograma de frecuencias `N_k` sobre las `Q` consultas de prueba.
> **Anti-Hub Fraction** — Vectores con `N_k = 0` dividido el tamaño total de la muestra
> evaluada.

with `Q = 200`, `K = 10`, and thresholds warn `> 0.25` / fail `> 0.40` for the anti-hub
fraction.

**This cannot pass.** With `Q = 200` and `K = 10`, at most `Q × K = 2,000` distinct vectors can
appear in any result. On a 1M-vector corpus, the anti-hub fraction is therefore at least
`1 - 2000/1000000 = 0.998` — catastrophically above the fail threshold — on a perfectly healthy
index. Even on a 20,000-vector corpus the floor is `0.90`. The metric would fire on every
target it was ever pointed at, and the first thing any user would do is disable it.

The thresholds themselves reveal where the definition drifted. Warn `0.25` / fail `0.40` only
make sense in a regime where `N_k` is computed with **every point in the dataset acting as a
query**, not over `Q = 200` probes. The thresholds are from one regime; the definition is from
another.

> ~~Warn `0.25` / fail `0.40` are recognisable values from the hubness literature.~~
> **Struck (MI-03): the attribution is false.** The founding hubness reference —
> Radovanović, Nanopoulos & Ivanović, *Hubs in Space: Popular Nearest Neighbors in
> High-Dimensional Data*, JMLR 11:2487–2531 (2010) — measures hubness as the **skewness of
> `N_k`** (the standardised third moment, `S_Nk`) and defines anti-hubs as points with
> `N_k = 0`. It publishes neither of these thresholds, and "top-1% hub share" does not
> appear in that body of work. The values were inherited from the source specification with
> no traceable provenance. P8-02 replaced them with measured ones; that is what they rest
> on now.

The **regime** correction is the part worth keeping. The threshold values were not.

There is also a conceptual reason the two must be separated. Canary recall asks *"is the engine
returning what brute force says it should?"* — a question about the index, best answered with
production-representative queries. Hubness asks *"is this embedding space topologically
pathological?"* — a question about the vector space itself, which requires every point to have a
chance to be someone's neighbour. Sharing a sampling regime between two different questions was
always going to break one of them.

## Decision

Hubness gets its own sampling regime, fully decoupled from canary recall.

```text
S      = deterministic random sample of live vector ids   (default 20_000)
k_hub  = neighbour count for hubness                      (default 10)

For each x in S: compute its exact k_hub nearest neighbours within S, excluding x itself.
N_k(x)      = number of times x appears in the other points' neighbour lists
total_slots = |S| · k_hub          (invariant: sum(N_k) == total_slots)

hub_share_top1pct = sum of the ceil(0.01·|S|) largest N_k values / total_slots
antihub_fraction  = |{x ∈ S : N_k(x) == 0}| / |S|
```

Supporting rules:

- **Guards.** `|S| < 1,000` → `UNAVAILABLE` (top 1% would be under 10 vectors and the metric is
  noise). `k_hub >= |S|` → `UNAVAILABLE`.
- **Comparability.** Measured hubness depends on `|S|`: fewer competitors means fewer chances to
  be a neighbour. `|S|` and `k_hub` are always recorded; baseline comparison across different
  values is refused with `not_comparable`; differing from the calibration point sets the report
  warning `thresholds_uncalibrated_for_sample_size`.
- **Source.** Default `truth` (ground-truth neighbours, measuring intrinsic hubness of the
  embedding space, engine-independent). `--hubness-source engine` measures effective hubness as
  served, including index error.
- **Cost.** `S = 20,000`, `D = 768` is roughly 3×10¹¹ FLOP — seconds with BLAS. The `S × S`
  matrix is never materialised; the same blocked reduction as ground truth is used.

## Consequences

**Buys:** two metrics that can actually pass on healthy data and fail on pathological data,
calibrated against a regime where published thresholds have meaning. Intrinsic hubness also
becomes engine-independent, which enables the cross-engine consistency check in `P7-07` — the
same corpus in four engines must produce the same hub share, and a disagreement is a real bug
in an adapter.

**Costs:**
- A second sampling stage and a second expensive computation, though ground truth machinery is
  shared.
- The metrics are not scale-free, and we have to say so. This is the honest position and it will
  generate questions; `P8-01` publishes sensitivity curves so the answer is a chart rather than
  an apology.
- Sub-sampling slightly *understates* hubness relative to the full corpus, since a point has
  fewer competitors. Consistent at fixed `S`, and therefore fine for trend detection, but not
  an absolute measure of the full corpus. Documented rather than hidden.

## Alternatives considered

- **Keep the specified definition and lower the thresholds to match.** Rejected: the metric
  would be a function of `Q × K / N` — essentially a measure of our own sampling — and would
  change meaning with corpus size. It would be a number, not a measurement.
- **Use all `N` points as queries.** Correct in principle, `O(N²)` in practice. At 1M vectors
  that is 10¹² distance computations. Rejected on cost; sub-sampling is the standard and accepted
  approach in the literature.
- **Normalise the anti-hub fraction by `min(N, Q·K)`.** Rejected: produces a bounded number that
  does not measure hubness, only sampling coverage.
- **Drop the hubness metrics entirely.** Tempting for MVP simplicity, but rejected: hubness is
  the one pathology no engine will ever report, which makes it the most differentiated thing the
  tool measures.

## Revisit if

- `P8-01` calibration shows the default `S = 20,000` is inadequate to separate healthy from
  pathological corpora, in which case adjust the default and re-derive the thresholds together.
- A published method for unbiased extrapolation from a subsample to full-corpus hubness becomes
  available — note it would need to satisfy [ADR-0003](0003-empirical-metrics-only.md).
