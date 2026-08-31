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
| [reports/](reports/) | Short per-dataset summary |

`UNAVAILABLE` rows have an empty `value` and a non-empty `unavailable_reason`. Never `0.0`.

Canary recall on an exact index with corpus-sourced queries is below `1.0` at the
default `k=10` (~`0.9`): the query id occupies one return slot and is then
stripped (self-exclusion). That is a pipeline sampling fact, not index damage.
Thresholds stay untouched until P8-02.
