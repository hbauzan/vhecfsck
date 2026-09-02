# Calibrated Default Thresholds and Dimensionality Profiles

**Status:** Calibrated in P8-02; measurements republished in MI-07  
**Provenance:** Measured across Gaussian controls ($d \in \{64, 128, 384, 768, 1536\}$), synthetic scenario pathologies (`healthy`, `drifted`, `tombstoned`, `hubby`), and public corpora (`sift-128`, `gist-960`, `glove-100`). `sentence-minilm` was skipped (`sentence-minilm.npy` not in cache).  
**Affects:** `vhecfsck/config.py`, `vhecfsck/pipeline.py`, ADR-0011.

---

## Executive Summary

Absolute metric thresholds inherited from the source specification (`roadmap/02-metrics-spec.md`) assume fixed values across all vector dimensions. Empirical measurement in **P8-01** demonstrated that while recall and deletion metrics (`canary_recall`, `dfi`) are invariant to dimension $d$, hubness and partition clustering variance naturally scale with $d$.

To eliminate false-positive warnings on healthy high-dimensional vector indexes:
1. **`canary_recall` and `dfi`** preserve their inherited global defaults across all dimensions.
2. **`hub_share_top1pct`, `antihub_fraction`, and `partition_size_cv`** use per-dimensionality profiles (`low`, `medium`, `high`, `ultra_high`).
3. Explicit user overrides (`AuditConfig.thresholds`, CLI flags, env vars, config files) take precedence over all calibrated defaults.

> **What this calibration does and does not establish.** Every threshold below is
> derived from measured healthy controls, so the **false-positive** rates are backed by
> data. The **false-negative** side is established for four of five metrics that have a
> pathological positive in this reference run: `canary_recall` (`0.5340` FAIL on
> `synthetic-tombstoned`), `dfi` (`0.3500` FAIL on the same), `hub_share_top1pct`
> (`0.9297` FAIL on `synthetic-hubby`), and `antihub_fraction` (`0.6450` FAIL on
> the same). `partition_size_cv` still has no pathological positive past the WARN
> floor (`synthetic-drifted` `0.9160` OK), so its detection sensitivity stays
> unvalidated — a gap in the synthetic operator, not evidence that the metric
> fails to detect. See
> [`roadmap/archive/plans/plan_integridad_matematica.md`](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/archive/plans/plan_integridad_matematica.md).

---

## Metric Calibration Breakdown

### 1. `canary_recall` (Canary Search Recall)
- **Gating Direction:** `lower_is_worse` (higher is better)
- **Calibrated Default:** Warn `< 0.85`, Fail `< 0.70` (Global, All $d$)
- **Measured Healthy Range:** `0.8985` to `0.9000` (FPR = `0.0%`; min is `gist-960`, gaussians and the other measured publics are `0.9000`)
- **Measured Pathological Range:** `0.5340` on `synthetic-tombstoned` 35% churn (FNR = `0.0%` at fail threshold `0.70`)
- **Invalidation / Boundary Conditions:**
  - Extremely acuminate query filters reducing eligible vector space below $k+1$.
  - Enforcing $Q < 5$ queries yields `UNAVAILABLE` status (ADR-0004 / lesson 32).

### 2. `dfi` (Deletion Fragmentation Index)
- **Gating Direction:** `higher_is_worse` (lower is better)
- **Calibrated Default:** Warn `> 0.15`, Fail `> 0.30` (Global, All $d$)
- **Measured Healthy Range:** `0.0000` (zero tombstones / zero uncollected dead tuples; FPR = `0.0%`)
- **Measured Pathological Range:** `0.3500` on `synthetic-tombstoned` (FNR = `0.0%` at fail threshold `0.30`)
- **Invalidation / Boundary Conditions:**
  - Engines lacking tombstone or deleted-vector telemetry return `UNAVAILABLE` (ADR-0013 / lesson 47).

### 3. `partition_size_cv` (IVF Partition Size Coefficient of Variation)
- **Gating Direction:** `higher_is_worse` (lower is better)
- **Calibrated Profiles:**
  - $d \le 384$ (`low`/`medium`): Warn `> 1.20`, Fail `> 2.00`
  - $384 < d \le 1024$ (`high`): Warn `> 1.30`, Fail `> 2.10`
  - $d > 1024$ (`ultra_high`): Warn `> 1.50`, Fail `> 2.25`
- **Measured Healthy Range:**
  - $d = 16$: `0.4846` (`synthetic-healthy`)
  - $d = 64$: `0.1785` (`gaussian-64`)
  - $d = 128$: `0.3394` (`gaussian-128`)
  - $d = 384$: `0.7152` (`gaussian-384`)
  - $d = 768$: `1.1048` (`gaussian-768`)
  - $d = 1536$: `1.3647` (`gaussian-1536`)
- **Measured FPR:** `0.0%` false positives across all healthy IVF clustering runs when profiled by $d$.
- **Measured FNR:** **not measured — no pathological positive past the WARN floor
  exists in this reference run.** `synthetic-drifted`, the scenario named for appends
  into existing IVF cells without a centroid refit (`lance#4164`), reports
  `0.9160 OK` (WARN floor `1.20` at $d=16$). The operator moves the metric relative
  to a refit, but not past the gate. Detection sensitivity therefore stays
  unvalidated.
- **Invalidation / Boundary Conditions:**
  - Non-partitioned indexes (FLAT, HNSW without IVF) return `UNAVAILABLE` / `not_applicable`.

### 4. `hub_share_top1pct` (Top-1% In-Degree Share)
- **Gating Direction:** `higher_is_worse` (lower is better)
- **Calibrated Profiles:**
  - $d \le 64$ (`low`): Warn `> 0.20`, Fail `> 0.35`
  - $64 < d \le 384$ (`medium`): Warn `> 0.28`, Fail `> 0.42`
  - $384 < d \le 1024$ (`high`): Warn `> 0.32`, Fail `> 0.45`
  - $d > 1024$ (`ultra_high`): Warn `> 0.35`, Fail `> 0.48`
- **Measured Healthy Isotropic Gaussian Control Distribution:**
  - $d = 64$: `0.1646`
  - $d = 128$: `0.2278`
  - $d = 384$: `0.2664`
  - $d = 768$: `0.3012`
  - $d = 1536$: `0.3126`
- **Measured FPR:** `0.0%` false positives on isotropic Gaussian controls under per-dimension profiling (reduced from 100% false-positive rate under static 0.20 default for $d \ge 128$). All five gaussian rows in this run are `OK`, including `gaussian-768` `0.3012` against the `high` WARN floor `0.32`.
- **Measured FNR:** `0.0%` at fail threshold `0.35` (`low`, $d=64$). Pathological
  positive: `synthetic-hubby` size=small, $n=8020$, `hub_share_top1pct = 0.9297`
  `FAIL` (`results.csv` value `0.9296758105`). Overall verdict on that row is
  `WARN` because evidence is `LOW` (`|S| < 10000`), not because the metric missed.
- **Invalidation / Boundary Conditions:**
  - Hubness sample size $|S| < 1000$ yields `UNAVAILABLE` (ADR-0006).
  - Hubness sampling parameters differing from $S=20000, k_{hub}=10$ set `thresholds_uncalibrated_for_sample_size` flag.

### 5. `antihub_fraction` (Orphan / Anti-Hub Vector Fraction)
- **Gating Direction:** `higher_is_worse` (lower is better)
- **Calibrated Profiles:**
  - $d \le 64$ (`low`): Warn `> 0.25`, Fail `> 0.40`
  - $64 < d \le 384$ (`medium`): Warn `> 0.39`, Fail `> 0.50`
  - $384 < d \le 1024$ (`high`): Warn `> 0.43`, Fail `> 0.55`
  - $d > 1024$ (`ultra_high`): Warn `> 0.46`, Fail `> 0.58`
- **Measured Healthy Isotropic Gaussian Control Distribution:**
  - $d = 64$: `0.2226`
  - $d = 128$: `0.2958`
  - $d = 384$: `0.3814`
  - $d = 768$: `0.4177`
  - $d = 1536$: `0.4376`
- **Measured FPR:** `0.0%` false positives on isotropic Gaussian controls under per-dimension profiling (reduced from 100% false-positive rate under static 0.25 default for $d \ge 128`). All five gaussian rows in this run are `OK`, including `gaussian-768` `0.4177` against the `high` WARN floor `0.43` (that row was `FAIL` under the old static `0.25` floor).
- **Measured FNR:** `0.0%` at fail threshold `0.40` (`low`, $d=64$). Pathological
  positive: `synthetic-hubby` size=small, $n=8020$, `antihub_fraction = 0.6450`
  `FAIL` (`results.csv` value `0.6450124688`). Overall verdict on that row is
  `WARN` because evidence is `LOW` (`|S| < 10000`), not because the metric missed.
- **Invalidation / Boundary Conditions:**
  - Hubness sample size $|S| < 1000$ yields `UNAVAILABLE`.

---

## Per-Dimensionality Threshold Profiles Table

| Profile | Dimension $d$ | `canary_recall` (W / F) | `hub_share` (W / F) | `antihub` (W / F) | `dfi` (W / F) | `partition_cv` (W / F) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `low` | $d \le 64$ | 0.85 / 0.70 | 0.20 / 0.35 | 0.25 / 0.40 | 0.15 / 0.30 | 1.20 / 2.00 |
| `medium` | $64 < d \le 384$ | 0.85 / 0.70 | 0.28 / 0.42 | 0.39 / 0.50 | 0.15 / 0.30 | 1.20 / 2.00 |
| `high` | $384 < d \le 1024$ | 0.85 / 0.70 | 0.32 / 0.45 | 0.43 / 0.55 | 0.15 / 0.30 | 1.30 / 2.10 |
| `ultra_high` | $d > 1024$ | 0.85 / 0.70 | 0.35 / 0.48 | 0.46 / 0.58 | 0.15 / 0.30 | 1.50 / 2.25 |
