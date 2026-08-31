# vhecfsck

Read-only, empirical, offline auditor for vector indexes that detects silent recall decay and index pathologies before they reach production.

![vhecfsck demo](docs/assets/vhecfsck-demo.gif)

## Quickstart

Run the interactive CLI demonstration from any machine with Python ≥ 3.11:

```bash
uvx vhecfsck demo
```

Or from a local checkout:

```bash
uv run vhecfsck demo
```

---

## The Problem

Vector database dashboards show green HTTP status and low latency while search quality silently degrades due to unindexed deletions, centroid drift, or graph fragmentation.

Production workloads encounter silent recall decay across major vector engines, as documented in [Qdrant #7147](https://github.com/qdrant/qdrant/issues/7147) (tombstone accumulation degrading search precision), [pgvector #244](https://github.com/pgvector/pgvector/issues/244) (HNSW graph disconnected components post-deletion), [Lance #4164](https://github.com/lancedb/lance/issues/4164) (IVF partition centroid drift after out-of-order appends), and table-level tombstone accumulation under default IVFFlat lists.

`vhecfsck` executes empirical audit queries against exact ground truth to detect and quantify these silent pathologies without modifying target database state.

### Explicit Limitations

* **3D Projection**: Spatial visualizer output is a lossy projection for visual intuition, not an exact spatial distance metric.
* **Corpus-Drawn Queries**: Recall bounds derived from corpus vectors represent an optimistic upper bound compared to external query distributions.
* **Hubness Thresholds**: Hub share and antihub fraction metrics depend on dimensionality $d$ and sample size $|S|$ (calibrated via threshold profiles).
* **pgvector DFI**: Deletion Fragmentation Index on PostgreSQL is a table-level proxy based on `n_dead_tup` statistics rather than exact per-segment tombstone inspection.

---

## What the Tool Measures

`vhecfsck` measures five core index health metrics against exact ground truth calculations:

| Metric | Target Pathology | Warn Threshold | Fail Threshold | Direction |
| :--- | :--- | :--- | :--- | :--- |
| **Canary Recall** | Silent recall decay | `< 0.85` | `< 0.70` | Lower is worse |
| **Hub Share (top 1%)** | Hubness / central point dominance | `> 0.20` | `> 0.35` | Higher is worse |
| **Antihub Fraction** | Orphaning / unreachable vectors | `> 0.25` | `> 0.40` | Higher is worse |
| **Deletion Fragmentation Index (DFI)** | Tombstone accumulation | `> 0.15` | `> 0.30` | Higher is worse |
| **Partition Size CV** | IVF centroid imbalance / skew | `> 1.20` | `> 2.00` | Higher is worse |

For full metric mathematical formulations, see [`roadmap/02-metrics-spec.md`](roadmap/02-metrics-spec.md).

---

## CI Integration & Exit Codes

Integrate `vhecfsck` into CI/CD pipelines to block deployments when index quality degrades.

### Exit Codes

| Exit Code | Label | Description |
| :---: | :--- | :--- |
| **`0`** | **`OK`** | All enabled metrics pass thresholds. |
| **`1`** | **`WARN`** | One or more metrics breached warning thresholds. |
| **`2`** | **`FAIL`** | One or more metrics breached failure thresholds. |
| **`3`** | **`INCONCLUSIVE`** | Audit cannot determine state (unsupported capability or insufficient sample size). |
| **`4`** | **`USAGE`** | CLI argument error, target connection failure (`TargetConnectionError`), or memory budget exceeded (`ResourceError`). |
| **`70`** | **`INTERNAL`** | Unhandled internal error. |

### CI Recipe (GitHub Actions)

```yaml
name: Audit Vector Index

on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Run Index Audit
        run: |
          uvx vhecfsck audit postgres://user:pass@localhost:5432/vectors \
            --only canary_recall,dfi \
            --format text
```

For GitLab CI, Kubernetes `CronJob`, and Prometheus textfile recipes, see [CI Integration Guide](docs/ci-integration.md).

---

## Engine Capability Matrix

Different target engines expose different level of introspection capabilities. Unsupported capabilities return `UNAVAILABLE` (exit code `3`) rather than fake values.

| Capability | Synthetic | LanceDB / Lance | Qdrant | Postgres / pgvector |
| :--- | :--- | :--- | :--- | :--- |
| **Exact k-NN Ground Truth** | Yes | Yes (native / compute) | Yes (brute force) | Yes (sequential scan) |
| **Canary Recall** | Yes | Yes | Yes | Yes |
| **Hubness Analysis** | Yes | Yes | Yes | Yes |
| **DFI (Tombstones)** | Yes | Yes (exact `_rowid`) | Partial (segment telemetry) | Proxy (`n_dead_tup`) |
| **Partition Size CV** | Yes | Yes (IVF lists) | `UNAVAILABLE` | Partial (catalog stats) |

See [Consolidated Capability Matrix](docs/engines/capability-matrix.md) and individual engine guides ([LanceDB](docs/engines/lancedb.md), [Qdrant](docs/engines/qdrant.md), [pgvector](docs/engines/pgvector.md)).

---

## Read-Only Guarantee & Zero Egress

`vhecfsck` is 100% read-only and designed for secure, air-gapped environments:

* **Zero Writes**: Never executes `VACUUM`, `REINDEX`, `INSERT`, `UPDATE`, or `DELETE`.
* **Zero Network Egress**: No telemetry, analytics, tracking, or external asset downloads.
* **Database Isolation**: PostgreSQL sessions enforce `default_transaction_read_only=on` and `Connection.read_only = True`.
* **Snapshot Assurance**: File-backed engines (LanceDB) verify zero disk modifications via SHA-256 snapshots and `chmod -R a-w` read-only mounts.

See [Read-Only Assurance](docs/read-only.md) and [SECURITY.md](SECURITY.md).

---

## Measured Performance

All published numbers are measured on designated reference hardware (Apple Silicon 8-core CPU, macOS 26.5, Python 3.11.15, Apple Accelerate BLAS):

| Stage / Component | Input Scale | Measured Duration | Peak RSS | Budget Ceiling | Status |
| :--- | :--- | ---: | ---: | ---: | :--- |
| **Ground Truth (`exact_knn`)** | $100,000 \times 768$ | 0.6974 s | 1,832.22 MB | 5.0 s | Pass |
| **Ground Truth (`exact_knn`)** | $1,000,000 \times 768$ | 5.7620 s | 1,861.86 MB | 20.0 s | Pass |
| **Hubness Subsample ($S=20k$)** | $20,000 \times 768$ | 0.6125 s | 1,980.20 MB | 3.0 s | Pass |
| **Deterministic 3D Projection** | $1,000,000 \times 768$ | 0.1611 s | 4,323.00 MB | 2.0 s | Pass |
| **Full Audit End-to-End** | $100,000 \times 768$ | 0.2045 s | 4,323.00 MB | 5.0 s | Pass |

See [docs/performance.md](docs/performance.md) for benchmark instructions.

---

## Installation & Extras

### Quickstart

```bash
uvx vhecfsck demo
```

### Package Installation

```bash
pip install vhecfsck
```

### Engine Extras

```bash
pip install "vhecfsck[lancedb]"
pip install "vhecfsck[qdrant]"
pip install "vhecfsck[postgres]"
pip install "vhecfsck[server]"
```

Or using `uv`:

```bash
uv add "vhecfsck[lancedb,qdrant,postgres]"
```

---

## Documentation & References

* **Metrics Specification**: [`roadmap/02-metrics-spec.md`](roadmap/02-metrics-spec.md)
* **Read-Only Assurance**: [`docs/read-only.md`](docs/read-only.md)
* **Performance Guidance**: [`docs/performance.md`](docs/performance.md)
* **Calibration Data**: [`docs/calibration/README.md`](docs/calibration/README.md)
* **Contributing Panel**: [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Licence & Credit

Copyright © **hbauzan**. Published under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for details.
