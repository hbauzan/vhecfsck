# ADR-0003 — Empirical metrics only; no abstract estimators

**Status:** Accepted
**Affects:** P2, P8

## Context

The pathologies this tool detects — distance concentration, hubness, distribution drift — have
a rich statistical literature full of sophisticated instruments: kernel density estimation,
maximum mean discrepancy, intrinsic dimensionality estimators, Kolmogorov–Smirnov tests on
distance distributions.

Every one of them shares a fatal property for this use case: when an on-call engineer asks
"why is this number 0.61 and should I care?", the answer requires explaining a bandwidth
parameter, a kernel choice, or a null hypothesis. An SRE who cannot verify a number will not
act on it, and a metric nobody acts on is dead weight in a pipeline.

There is a second, more practical problem. An estimator has no ground truth. If our MMD
implementation has a bug, nothing in the test suite can tell, because there is no independent
answer to compare against — only another implementation with its own assumptions.

## Decision

Every reported number is a count, a ratio, or a direct measurement against brute-force ground
truth. Specifically:

- **Recall** is measured against exact k-NN computed by full matrix multiplication. Not
  estimated, not sampled-and-extrapolated — actually computed.
- **DFI** is a division of two integers the engine reports.
- **Hub share and anti-hub fraction** are integer counts over an exhaustively computed
  neighbour graph on the sample.
- **Partition CV** is a standard deviation over a list of integers.

The consequence that makes this decision worth its cost: **every metric has a naive `O(N²)`
reference implementation**, so every optimised implementation has an exact oracle to be
differentially tested against (`P2-03`). Correctness becomes checkable rather than argued.

Two things are permitted and are not violations:

- **Bootstrap resampling** for confidence intervals. This resamples observed data and assumes
  no distribution; it is arithmetic over measurements we already made.
- **MAD-based outlier flagging** for the hub diagnostics. This is a median of absolute
  deviations — a count-and-sort operation — used only for a reported diagnostic, never for a
  gated metric.

## Consequences

**Buys:**
- Every number is explainable in one sentence and reproducible with a few lines of NumPy.
- Every metric is testable against an independent oracle, which is the entire basis of the
  quality claims in [`testing-strategy.md`](../testing-strategy.md).
- No hidden hyperparameters, so no tuning knobs that quietly change the verdict.

**Costs:**
- Compute. Exact ground truth is `O(Q · N · D)` and exact hubness is `O(S² · D)`, where an
  estimator would be far cheaper. This is the direct cause of the ~1M single-node ceiling in
  [ADR-0005](0005-ground-truth-precision-and-blocking.md) and of the sampling regime in
  [ADR-0006](0006-hubness-sampling-regime.md).
- Sampling honesty becomes load-bearing. Because we refuse to extrapolate, we must be explicit
  about what the sample does and does not support — hence `evidence_strength` and the
  comparability constraints.
- Some genuinely useful signals are unavailable. Detecting a *distributional* shift between two
  corpora is what MMD is actually good at, and we give that up.

## Alternatives considered

- **Estimators with published defaults.** Rejected: the "why is this number what it is?"
  conversation is unwinnable with an operations audience, and the correctness of the
  implementation would be untestable.
- **A hybrid — empirical gating, estimators as advisory extras.** Rejected for now on complexity
  grounds, but this is the natural relaxation if a compelling need appears. It would need its own
  ADR and a clear visual separation in the report so an advisory number is never mistaken for a
  gated one.
- **Sampling with extrapolation to a full-corpus estimate.** Rejected: reporting an estimate as
  if it were a measurement is exactly the dishonesty this decision exists to prevent. We report
  what we measured, on the sample we measured it on, and say so.

## Revisit if

- A pathology is identified that is genuinely undetectable by counting, and users are hitting it.
  In that case add it as an explicitly-labelled advisory metric, never as a gated one.
- Corpus sizes routinely exceed the exact-computation ceiling such that sampling with a
  published confidence interval becomes the only option — note that bootstrap intervals over
  measured samples remain compatible with this decision.
