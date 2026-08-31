# ADR-0011 — Configurable thresholds plus baseline/delta gating

**Status:** Accepted (calibrated in `P8-02`)
**Affects:** P0, P2, P8
**Corrects:** source specification defect 7

## Amendment (P8-02 Calibration Results)

Empirical measurements from **P8-01** / **P8-02** over isotropic Gaussian controls ($d \in \{16, 64, 128, 384, 768, 1536\}$), synthetic pathologies, and public corpora confirmed that `canary_recall` (warn `< 0.85`, fail `< 0.70`) and `dfi` (warn `> 0.15`, fail `> 0.30`) are dimension-invariant and justified.

For hubness metrics (`hub_share_top1pct`, `antihub_fraction`) and partition variance (`partition_size_cv`), measurements proved that hubness and cluster size variance scale with dimension $d$. A single global default caused 100% false-positive rates on isotropic Gaussian controls for $d \ge 128$.

**Calibrated Per-Dimensionality Profiles (`vhecfsck/config.py`):**
- `low` ($d \le 64$): `hub_share` (0.20 / 0.35), `antihub` (0.25 / 0.40), `partition_cv` (1.20 / 2.00)
- `medium` ($64 < d \le 384$): `hub_share` (0.28 / 0.42), `antihub` (0.39 / 0.50), `partition_cv` (1.20 / 2.00)
- `high` ($384 < d \le 1024$): `hub_share` (0.32 / 0.45), `antihub` (0.43 / 0.55), `partition_cv` (1.30 / 2.10)
- `ultra_high` ($d > 1024$): `hub_share` (0.35 / 0.48), `antihub` (0.46 / 0.58), `partition_cv` (1.50 / 2.25)

Full calibration documentation and error rate analyses are published in [`docs/calibration/thresholds.md`](../../docs/calibration/thresholds.md).

## Context

The source specification presents absolute thresholds as universal facts: recall warn `< 0.85`,
DFI warn `> 0.15`, hub share warn `> 0.20`, anti-hub warn `> 0.25`, partition CV warn `> 1.20`.
They are plausible values, and the recall ones in particular match common operational intuition.
But no measurement is offered for any of them, and at least three are known to be
dataset-dependent in ways that matter:

- **Hubness rises with dimensionality.** A healthy 1536-dimensional corpus will show a higher hub
  share than a healthy 128-dimensional one. One global threshold cannot serve both, and
  [ADR-0006](0006-hubness-sampling-regime.md) establishes that these metrics additionally depend
  on the sample size.
- **Partition CV depends on how clustered the data is.** k-means on real embeddings routinely
  produces a CV in the 0.3–0.6 range even when perfectly healthy, so `1.20` may be either
  reasonable or far too loose depending on the corpus — and nobody has checked.
- **Acceptable recall depends on the application.** 0.85 is a disaster for legal document
  retrieval and irrelevant for a "related posts" sidebar.

The failure mode is asymmetric and well documented in operations practice: a check that produces
false positives gets disabled, and a disabled check protects nothing. That makes an uncalibrated
threshold worse than a missing one.

## Decision

**Three layers, in increasing order of trustworthiness.**

**1. Thresholds are configuration, not code.** Defaults live in `config.py` with a comment
pointing at [`02-metrics-spec.md`](../02-metrics-spec.md), and a test asserts the code matches the
documented table so the two cannot drift. Every threshold is overridable via config file, env
var, or CLI flag. Profiles are supported, including per-dimensionality profiles if `P8-02` shows a
single global default cannot work for the hubness metrics.

**2. Defaults will be calibrated, and the calibration published.** `P8-01` measures all five
metrics across reference corpora — uniform Gaussian at five dimensionalities, public ANN benchmark
datasets, and synthetic corpora with injected pathologies — and publishes healthy ranges,
sensitivity curves, and the measured false-positive and false-negative rates at the chosen
thresholds. `P8-02` adjusts defaults only where the evidence demands it.

The discipline that matters here: **do not tune thresholds until all reference data passes.** Some
public corpora are genuinely hubby. Reporting that honestly is the correct outcome, and quietly
raising a threshold until the warnings stop is how a checker becomes decorative.

**3. Baseline/delta mode, for corpora the defaults do not fit.** `vhecfsck baseline record`
captures a healthy state; `--baseline baseline.json` gates on *change* rather than on absolute
value. Delta thresholds default to the run-to-run variance measured in `P8-01`, so the gate sits
above noise rather than at a round number. `--gate absolute|delta|both` selects the policy.

Comparability is strictly enforced: a baseline recorded with a different seed, `k`,
`hubness_sample_size`, `k_hub`, metric space, dimension, or engine is refused with
`not_comparable` rather than silently compared. Recording a baseline from an already-degraded
index emits a warning, since it would bake the degradation in as normal.

**Honesty requirements in output:**
- The report always states which thresholds were applied and whether they were defaults.
- `thresholds_uncalibrated_for_sample_size` is set when hubness parameters differ from the
  calibration point. The number is still shown; it is simply not gated against defaults that do
  not apply to it.
- Every threshold's provenance is documented, including "inherited from the source specification,
  not yet independently measured" for as long as that remains true.

## Consequences

**Buys:** a tool that can be adopted incrementally on a corpus unlike anything in the calibration
set, and a defensible answer to the question every reviewer will ask — "where do these thresholds
come from?"

**Costs:**
- Baseline mode is real complexity: a second report to store, comparability rules, delta
  thresholds, and a `--gate` policy.
- Calibration requires downloading and processing public datasets, with the licence review that
  entails.
- Configurable thresholds mean two users can reach different verdicts on identical data. Mitigated
  by always recording the applied thresholds in the report.
- Until `P8-02` lands, the shipped defaults are inherited rather than measured. This must be
  stated in the docs, not glossed over.

## Alternatives considered

- **Ship the inherited thresholds as universal truth.** Rejected: unjustifiable to a technical
  audience, and probably wrong for at least the hubness metrics.
- **Baseline-only gating, no absolute thresholds.** Rejected: a first-time user with no baseline
  would get no verdict at all, which destroys the 60-second first impression.
- **Auto-calibrate on first run against the user's own corpus.** Rejected: cannot distinguish
  "healthy" from "already broken", so it would silently normalise an existing failure. A
  deliberate `baseline record` makes the assumption explicit and warns about it.
- **Machine-learned thresholds from aggregated user data.** Rejected: requires telemetry, which is
  permanently out of scope.

## Revisit if

`P8-02` produces the measurements — at which point this ADR is **amended** with the results and
the status updated from "measurements pending" to the final calibrated position. That amendment is
a required deliverable of `P8-02`, not optional.
