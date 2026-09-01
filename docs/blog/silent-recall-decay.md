# Silent Recall Decay: Why Your Vector Database Passes Health Checks While Serving Wrong Answers

*Published: 2026-09-01*

Vector databases are now central to modern retrieval-augmented generation (RAG) and search architectures. Yet, they suffer from a fundamental observability gap: **a vector index can silently degrade and return incorrect or empty results while every standard infrastructure metric stays 100% green.**

CPU usage, RAM allocation, QPS, p50 latency, and Kubernetes `/healthz` probes continue to report healthy status. Your API endpoint returns HTTP `200 OK` with valid JSON array payloads. But the items inside those arrays are topologically wrong, incomplete, or functionally invisible to users.

This post details the three core mechanisms driving silent recall decay, presents empirical evidence from production engine reproductions, and introduces `vhecfsck`: a 100% offline, read-only, empirical auditor designed to catch index corruption before it hits production.

---

## The Three Failure Mechanisms

Unlike relational databases where fragmentation increases I/O latency without altering query correctness, mutating a vector index alters the **retrieval topology itself**.

### 1. Tombstone Path Blocking in HNSW Graphs
Hierarchical Navigable Small World (HNSW) graphs construct proximity layers across high-dimensional vectors. Deleting vectors without rebuilding the graph leaves "tombstone" nodes behind. During beam search (`ef_search`), queries traverse these tombstoned nodes, consuming candidates from the beam budget. Once candidates are finalized, dead nodes are filtered out. If the top $K$ candidates were dead, the engine returns a short or empty result set (`[]`), even if live neighbours exist nearby.

* **Upstream Evidence**: [`pgvector/pgvector#244`](https://github.com/pgvector/pgvector/issues/244). On tables with high delete/update churn before `VACUUM`, dead tuples consume HNSW slots, dropping recall to **0.10** (a 90% loss of relevant items). In pgvector v0.8.0+, this is mitigated at query time via `hnsw.iterative_scan = relaxed_order`.

### 2. Centroid Drift and Unindexed Appends in IVF
Inverted File (IVF) indexes partition vector space into Voronoi cells using $K$-means centroids computed at build time. Appending new vectors without updating or re-clustering centroids causes two pathologies:
1. Centroids become imbalanced, turning fast cell lookups into expensive disk scans.
2. Appended vectors remain in unindexed table fragments, bypassing cell lookup entirely.

* **Upstream Evidence**: [`lancedb/lance#4164`](https://github.com/lancedb/lance/issues/4164). Appending 10× data without re-indexing leaves 90% of vectors unindexed ($N_{\text{live}} = 2,000$ vs $N_{\text{indexed}} = 200$), causing severe recall collapse on appended data.

### 3. High-Dimensional Hubness Skew
As vector dimensionality scales ($d \ge 768$), distance distribution collapses due to the curse of dimensionality. A small subset of vectors ("hubs") appears in the top nearest-neighbours of thousands of unrelated queries, while "anti-hubs" become topologically unreachable and are never retrieved by any query.

* **Upstream Evidence**: [`qdrant/qdrant#7147`](https://github.com/qdrant/qdrant/issues/7147). Multitenant subgraph consolidation can corrupt per-tenant recall while aggregate collection canaries remain green.

---

## Empirical Verification Summary

The table below summarizes measured baseline data captured by `vhecfsck` across automated reproduction harnesses on clean test environments:

| Reproduction Target | Metric | Degraded State | Remediated State | Engine Remediation |
| :--- | :--- | :--- | :--- | :--- |
| `pgvector#244` (HNSW) | `canary_recall` | 0.13 (FAIL, exit code 2) | 0.90 (OK) | `VACUUM` table / `hnsw.iterative_scan` |
| `lance#4164` (IVF) | `counts().indexed` ratio | 0.10 (90% unindexed gap) | 1.00 (0% gap) | `create_index(replace=True)` |
| `qdrant#7147` (Multitenant) | `canary_groups` recall | Group min recall decay | Group min 1.00 | Payload index optimization |

---

## Introducing `vhecfsck`

`vhecfsck` (**V**ector **H**ealth **E**mpirical **C**heck & **F**ile **S**ystem **C**heck) is an offline, read-only CLI tool that measures vector index health directly against brute-force ground truth.

### Key Guarantees

1. **Strictly Read-Only**: `vhecfsck` never issues `VACUUM`, `REINDEX`, or `OPTIMIZE` commands. It mounts datasets read-only or opens PostgreSQL connections with `default_transaction_read_only = on`.
2. **Empirical Metrics**: Every score is a direct mathematical measurement ($\mathcal{O}(N)$ canary recall, DFI ratio, Hubness top-1%, Partition CV) computed against an exact brute-force oracle.
3. **Zero Network Egress**: Runs 100% offline in CI/CD pipelines or local developer workstations.

### Quickstart

Run a zero-dependency local audit demo:

```bash
uvx vhecfsck demo
```

Audit a local LanceDB dataset:

```bash
uvx vhecfsck audit /path/to/dataset.lance
```

---

## Conclusion & Upstream Credit

Silent recall decay is not a design defect of any single engine; it is an inherent trade-off between write throughput, memory overhead, and indexing costs. We credit the engineering teams at **pgvector**, **LanceDB**, and **Qdrant** for active mitigations (such as pgvector's iterative HNSW scans in v0.8.0).

By running `vhecfsck` in CI/CD pipelines and production scheduled cronjobs, database operators can catch indexing regressions empirically before end users experience degraded search quality.
