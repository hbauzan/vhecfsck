# Calibration (P8-01)

Measured healthy / pathological ranges for the five metrics. Thresholds are **not**
changed here — that is [P8-02](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/archive/phases/phase-8-calibration-and-hardening.md).

## Regenerate

```bash
make calibrate
# equivalent:
uv run python scripts/calibrate.py --profile reference --out docs/calibration
```

Smoke (what the default test suite runs):

```bash
uv run python scripts/calibrate.py --profile smoke --out /tmp/vhecfsck-cal
```

Public ANN archives download on demand into `~/.cache/vhecfsck/calibration` (or `--cache`).
They are **not** committed. `--no-download` skips them with a reason instead of inventing `0.0`.

`nytimes-256` is licence-excluded (LDC2008T19). See [datasets.md](datasets.md).

## Artefacts

| File | What |
| :--- | :--- |
| [datasets.md](datasets.md) | Licence + provenance for every corpus |
| [results.csv](results.csv) | Baseline: all five metrics, one row per metric |
| [hubness_sensitivity.csv](hubness_sensitivity.csv) | Gaussian `S` × `k_hub` sweep |
| [hubness_sensitivity.md](hubness_sensitivity.md) | Same sweep as a table |
| [skipped.csv](skipped.csv) | Corpora not measured, with the reason |
| `reports/` | Short per-dataset summary (e.g., [synthetic-healthy.md](reports/synthetic-healthy.md)) |

`UNAVAILABLE` rows have an empty `value` and a non-empty `unavailable_reason`. Never `0.0`.

## Known gaps in this calibration

Read these before quoting a number from here.

**`partition_size_cv` still has no pathological positive past the WARN floor.**
`synthetic-drifted` measures `0.9160 OK` (CSV `0.9160348381`; WARN floor `1.20` at
$d=16$). The IVF freeze (MI-01) makes `partitions()` see the induced assignment, but
the value stays below WARN, so FNR for this metric is unmeasured.

**Hubness FNR is measured; overall on `synthetic-hubby` is still WARN.**
`synthetic-hubby` size=small, $n=8020$, $d=64$: `hub_share_top1pct = 0.9297 FAIL`
(CSV `0.9296758105`) and `antihub_fraction = 0.6450 FAIL` (CSV `0.6450124688`).
Both FAILs are `LOW` evidence because `|S| < 10000`, so overall is WARN, not FAIL.

**`sentence-minilm` was not measured.** `skipped.csv`: `sentence-minilm.npy not in
cache`. No `0.0` was invented. `nytimes-256` remains licence-excluded.

Healthy Gaussians in this run are `OK` against per-dimension profiles (for example
`gaussian-768 antihub_fraction 0.4177 OK` vs the `high` WARN floor `0.43`). Verdict
columns are from `run_audit` + `resolve_thresholds_for_dimension`, not the old
static `0.20` / `0.25` floors.

Canary recall on an exact index with corpus-sourced queries is below `1.0` at the
default `k=10` (~`0.9`): the query id occupies one return slot and is then
stripped (self-exclusion). That is a pipeline sampling fact, not index damage.
Thresholds were not retuned in MI-07.
