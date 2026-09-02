# Calibration (P8-01)

Measured healthy / pathological ranges for the five metrics. Thresholds are **not**
changed here — that is [P8-02](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/phases/phase-8-calibration-and-hardening.md).

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

**Three of the five metrics had no pathological positive in the last published
`results.csv`.** `hub_share_top1pct` and `antihub_fraction` now have one: `synthetic-hubby`
size=small measures `hub_share 0.9297 FAIL` / `antihub 0.6450 FAIL` (MI-02).
`partition_size_cv` on `synthetic-drifted` measures `0.9160 OK` after the IVF freeze
(MI-01) — the operator moves the metric, but not past the WARN floor. Republishing FNR
from a fresh `make calibrate` is MI-07. The previous published `0.0877 OK` / `0.1126 OK` /
`1.0342 OK` figures described operators that did not induce the gated geometry.

**The `state` and `verdict` columns of `results.csv` predate the per-dimension profiles.**
They were evaluated against the old static thresholds, which is why healthy Gaussian
controls appear as `WARN` / `FAIL` (for example `gaussian-768 antihub_fraction FAIL
0.4177`). The **values** are the calibration data and are correct — the thresholds in
[thresholds.md](thresholds.md) were derived from them. Only the verdict columns are stale.
Regenerating the run is tracked as MI-04.

Canary recall on an exact index with corpus-sourced queries is below `1.0` at the
default `k=10` (~`0.9`): the query id occupies one return slot and is then
stripped (self-exclusion). That is a pipeline sampling fact, not index damage.
Thresholds stay untouched until P8-02.
