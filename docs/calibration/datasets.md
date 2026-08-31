# Calibration datasets

Licences and provenance for every corpus the P8-01 harness knows about.
Source vectors are **not** in git. Derived statistics live in `results.csv`.

Regenerate this file with `uv run python scripts/calibrate.py --profile smoke --out docs/calibration` (catalogue only changes when `CATALOG` in `scripts/calibrate.py` changes).

| ID | Family | Status | SPDX | Licence (short) | Provenance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gaussian-64` | gaussian | generated | `LicenseRef-Generated` | Generated in-process; no third-party corpus. | numpy Generator.standard_normal, seed from the calibration profile. Theoretical hubness control (ADR-0006 / P8-01). |
| `gaussian-128` | gaussian | generated | `LicenseRef-Generated` | Generated in-process; no third-party corpus. | numpy Generator.standard_normal, seed from the calibration profile. Theoretical hubness control (ADR-0006 / P8-01). |
| `gaussian-384` | gaussian | generated | `LicenseRef-Generated` | Generated in-process; no third-party corpus. | numpy Generator.standard_normal, seed from the calibration profile. Theoretical hubness control (ADR-0006 / P8-01). |
| `gaussian-768` | gaussian | generated | `LicenseRef-Generated` | Generated in-process; no third-party corpus. | numpy Generator.standard_normal, seed from the calibration profile. Theoretical hubness control (ADR-0006 / P8-01). |
| `gaussian-1536` | gaussian | generated | `LicenseRef-Generated` | Generated in-process; no third-party corpus. | numpy Generator.standard_normal, seed from the calibration profile. Theoretical hubness control (ADR-0006 / P8-01). |
| `synthetic-healthy` | synthetic | generated | `LicenseRef-Generated` | Generated in-process (vhecfsck synthetic). | vhecfsck.synthetic.scenarios.scenario_healthy |
| `synthetic-drifted` | synthetic | generated | `LicenseRef-Generated` | Generated in-process (vhecfsck synthetic). | vhecfsck.synthetic.scenarios.scenario_drifted (lance#4164 analogue) |
| `synthetic-tombstoned` | synthetic | generated | `LicenseRef-Generated` | Generated in-process (vhecfsck synthetic). | vhecfsck.synthetic.scenarios.scenario_tombstoned (pgvector#244 analogue) |
| `synthetic-hubby` | synthetic | generated | `LicenseRef-Generated` | Generated in-process (vhecfsck synthetic). | vhecfsck.synthetic.scenarios.scenario_hubby |
| `sift-128` | public | download | `CC0-1.0` | TEXMEX / INRIA: Laurent Amsaleg and Hervé Jégou waived copyright to the extent possible under law (CC0-like waiver published from France)... | http://corpus-texmex.irisa.fr/ — ANN_SIFT1M sift.tar.gz, sift_base.fvecs |
| `gist-960` | public | download | `CC0-1.0` | Same TEXMEX waiver as SIFT1M. Cite Jegou, Douze, Schmid, IEEE TPAMI 2011. | http://corpus-texmex.irisa.fr/ — ANN_GIST1M gist.tar.gz, gist_base.fvecs |
| `glove-100` | public | download | `PDDL-1.0` | Pre-trained vectors: Open Data Commons PDDL 1.0. | https://nlp.stanford.edu/projects/glove/ — glove.6B.zip / glove.6B.100d.txt |
| `nytimes-256` | public | excluded | `LicenseRef-LDC-NYT` | Derived from The New York Times Annotated Corpus (LDC2008T19). LDC terms forbid redistribution and restrict use to non-commercial linguis... | https://catalog.ldc.upenn.edu/LDC2008T19 via ann-benchmarks nytimes-256-angular |
| `sentence-minilm` | public | cache_only | `Apache-2.0` | Operator must record the corpus and model licences in a sidecar. all-MiniLM-L6-v2 weights are Apache-2.0; Wikipedia-derived text is CC BY... | Cache file sentence-minilm.npy (shape (n, d) float32). No default host: a 35M-row Wikipedia MiniLM dump is tens of GB... |

## Notes

- **synthetic-healthy:** Positive control for a healthy IVF build.
- **sift-128:** Prefix of N vectors from the official base split; vectors are not committed.
- **gist-960:** Archive is ~2.6 GB; stream the prefix then stop. Vectors are not committed.
- **glove-100:** Prefix of N rows (highest-frequency tokens). Rows are L2-normalised.
- **nytimes-256:** Excluded. Do not download or cache this corpus in the harness.
- **sentence-minilm:** Drop a permissively licensed npy into the cache to include this row.
