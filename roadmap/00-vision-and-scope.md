# 00 — Vision and Scope

## 1. The failure mode we exist to catch

Vector databases degrade in a way that no existing observability stack detects.

In a relational database, fragmentation costs you I/O latency but the rows you get back are
still correct. In a vector index, mutation degrades **the answers themselves**, and it does
so without touching a single signal that an SRE watches:

- CPU, memory, QPS, p50 latency, and Kubernetes liveness probes all stay green.
- The API keeps returning `200 OK` with a well-formed list of results.
- The list is simply *wrong*, or empty, and nothing in the system knows.

Three distinct mechanisms produce this outcome.

### 1.1 Tombstone path blocking in HNSW graphs

Rewiring edges in a navigable small-world graph on every delete is prohibitively
expensive, so engines mark deleted nodes as *tombstones* (Weaviate, Qdrant) or leave *dead
tuples* behind under MVCC (pgvector/PostgreSQL). Beam search still traverses those nodes,
spends its `ef_search` budget on them, and filters them out *after* the candidate list is
finalised. If the best `ef_search` candidates were all dead, the caller receives `[]` —
even though live, valid neighbours existed two hops away.

The pathology is worst exactly where it matters: high-churn collections, which are the ones
under active production use.

### 1.2 Centroid drift and partition imbalance in IVF

An IVF index partitions the space into `K` Voronoi cells via k-means at build time, and a
query only scans the `nprobe` cells nearest to it. Insert ten times more data without
retraining the centroids and the new vectors land unevenly. A cell sized for 500 vectors
ends up holding 80,000, and "scan the nearest cell" silently becomes "sequentially scan a
large chunk of the dataset from disk". p99 latency explodes, and recall drops because the
true neighbours now live in cells the query never probes.

### 1.3 Hubness in high-dimensional space

As dimensionality rises toward 768 or 1536, the variance of pairwise distances collapses —
every point is roughly the same distance from every other point. The distribution of
"how often is vector *x* somebody's nearest neighbour" (`N_k(x)`) becomes severely skewed.
A handful of vectors sit at topological crossroads and appear in the top-10 of thousands of
unrelated queries, cannibalising retrieval. Their mirror image, *anti-hubs*, are indexed
vectors that are never returned to anyone: content that exists, is paid for, and is
functionally invisible.

Hubness is not a bug in the engine. It is a property of the embedding space, which is
precisely why no engine will ever report it to you.

### 1.4 Evidence from the field

These are not hypotheticals. Four upstream issues anchor the problem and double as our
integration test corpus — each one becomes a reproduction scenario in the test suite.

| Anchor | Failure | Reproduced in | Re-verified |
| :--- | :--- | :--- | :--- |
| [`pgvector/pgvector#244`](https://github.com/pgvector/pgvector/issues/244) | Dead tuples drive recall to **0%** on tables with frequent updates/deletes before autovacuum runs. Mitigated in v0.8.0 via iterative scans. | [P7](phases/phase-7-qdrant-and-pgvector-adapters.md) | 2026-09-01 (v0.8.6) |
| [`lancedb/lance#4164`](https://github.com/lancedb/lance/issues/4164) | IVF indexes with a static `num_partitions` degrade to linear scan when the dataset grows 10× without repartitioning. | [P5](phases/phase-5-lancedb-adapter.md) | 2026-09-01 (v0.17.x) |
| [`qdrant/qdrant#7147`](https://github.com/qdrant/qdrant/issues/7147) | Segment consolidation corrupts per-tenant subgraphs (`is_tenant: true`), dropping mean precision from **0.98 to 0.61** with health checks fully green. | [P7](phases/phase-7-qdrant-and-pgvector-adapters.md) | 2026-09-01 (v1.19.0) |
| [`weaviate/weaviate#11951`](https://github.com/weaviate/weaviate/issues/11951), [`#8914`](https://github.com/weaviate/weaviate/issues/8914) | Entry-point repair selects tombstoned nodes, causing infinite loops and pod startups exceeding one hour. | P10 (Weaviate adapter, post-1.0) | Planned P10 |

> Verify each issue is still described accurately at the time you write the reproduction
> test. Upstream issues get fixed, retitled, and closed; a stale claim in our README is a
> credibility problem. See [P9](phases/phase-9-docs-release-and-launch.md), ticket `P9-04`.

## 2. Thesis

`vhecfsck` is a **read-only, empirical, offline auditor** for vector indexes. It answers one
question that no dashboard currently answers: *is this index still returning the right
answers?*

Three commitments define the product and constrain every design decision.

### 2.1 Strictly read-only

The tool inspects local index files and read-only APIs. It never writes, never locks
writers, never triggers compaction, never mutates an index, and never issues a `VACUUM`,
`REINDEX`, or `optimize`. This is not a soft preference — it is enforced structurally
(the adapter protocol has no write methods), verified by tests that hash the target before
and after an audit, and treated as the project's single most important invariant. A tool
that corrupts a user's production index once is dead forever.

See [ADR-0001](adr/0001-read-only-by-default.md).

### 2.2 Empirical, not abstract

Every number the tool reports is a count, a ratio, or a direct measurement against brute
force ground truth. There are no kernel density estimates, no maximum mean discrepancy, no
distributional assumptions that require a paper to defend. If a user asks "where does this
number come from?", the answer must be a sentence long and independently checkable with
NumPy.

This constraint has a practical payoff: every metric has a naive `O(N²)` reference
implementation, which means every optimised implementation has an exact oracle to be tested
against. See [ADR-0003](adr/0003-empirical-metrics-only.md).

### 2.3 Dual purpose: CI gate and visual showcase

The same audit engine serves two audiences through two front ends.

- **Retention** — a CLI with Unix exit codes (`0` OK, `1` WARN, `2` FAIL) and Prometheus
  output, designed to sit in a CI pipeline or a cron job and page someone when recall
  starts sliding. This is what makes the tool stay installed.
- **Showcase** — a GPU-accelerated 3D projection of the index topology: cannibalising hubs
  in red, invisible anti-hubs in blue, tombstones as translucent grey. This is what makes
  someone install it in the first place, and it is what makes an abstract failure mode
  legible in a screenshot.

Neither front end may contain metric logic. Both consume the same versioned report object.

## 3. Personas

| Persona | Context | What they need | Primary surface |
| :--- | :--- | :--- | :--- |
| **Platform / SRE engineer** | Owns a RAG stack in production, has been burned by a silent recall drop | A cron job or CI gate that fails loudly and a number to put on a dashboard | CLI + Prometheus |
| **ML / RAG engineer** | Debugging "why does retrieval feel worse than last month" | An explanation of *which* vectors are pathological and why | 3D visualizer + report |
| **Database / infra reviewer** | Evaluating whether to trust the tool near production | Proof of read-only behaviour, reproducible methodology | Docs + read-only audit |
| **Evaluator / new visitor** | Saw a GIF, has 60 seconds | A single command that shows the failure mode on synthetic data | `uvx vhecfsck demo` |

The `demo` path deserves special emphasis: it must require **no database, no credentials,
and no data**, because that is the difference between a tool people try and a tool people
bookmark.

## 4. In scope for v0.1.0 (MVP)

- Read-only auditing of a synthetic in-memory corpus and a LanceDB dataset.
- Five gated metrics: canary recall, deletion fragmentation index, top-1% hub share,
  anti-hub fraction, IVF partition size CV. Fully specified in
  [`02-metrics-spec.md`](02-metrics-spec.md).
- Exact brute-force ground truth via blocked BLAS, up to ~1M vectors × 768 dimensions on a
  single node.
- A synthetic dataset generator with **injectable, controllable pathologies** — the
  backbone of the test suite and of the demo.
- Versioned JSON report, human-readable terminal output, Prometheus textfile exporter.
- CLI: `audit`, `demo`, `serve`, `export`, with the documented exit-code contract.
- A 3D WebGL visualizer driven entirely by real report data.
- Public repo, Apache-2.0, CI, and a PyPI release installable with `uvx vhecfsck`.

## 5. Explicitly out of scope

Saying no here is what keeps the MVP finishable.

| Not doing | Why |
| :--- | :--- |
| **Any form of repair, reindex, vacuum, or optimisation** | Violates the read-only invariant. The tool diagnoses; the operator remediates. A `--advise` mode that *prints* the command a human could run is acceptable post-1.0. |
| **Being a vector database, or a query proxy** | Satellite tooling only. Nothing sits in the request path. |
| **Query-time interception / live traffic sampling** | Requires embedding in the application. Query logs may be supplied as a file instead. |
| **Weaviate, Milvus, Elasticsearch, FAISS, Chroma adapters** | Post-1.0. The adapter protocol is designed to accept them; implementing five adapters before proving one is scope suicide. |
| **Distributed / multi-node ground truth** | The 1M × 768 single-node ceiling is a deliberate boundary. Above it, sampling with a documented confidence interval, not a cluster. |
| **Embedding quality evaluation (NDCG, MRR against labelled relevance)** | Different problem. We measure whether the index faithfully reproduces its own brute-force answer, not whether the embedding model is good. |
| **Real-time continuous monitoring daemon** | Audits are expensive and periodic by nature. Cron plus Prometheus covers the need. |
| **A hosted SaaS, accounts, or telemetry of any kind** | No phone-home, ever. It runs next to production data. |
| **GPU acceleration for ground truth** | CPU BLAS meets the 1M ceiling. Optional post-1.0 if benchmarks justify it. |

## 6. Success criteria

The MVP is done when all of the following are objectively true.

**Correctness**
- Every metric matches a naive reference implementation exactly (or within a documented
  floating-point tolerance) on randomised inputs.
- Every metric is validated against synthetic datasets whose true value is known by
  construction.
- Two runs with the same seed produce byte-identical JSON reports.

**Safety**
- An audit of a LanceDB dataset leaves every file's content hash and mtime unchanged.
- No code path in `adapters/` can write, and this is enforced by the protocol's type
  signature plus a test that greps for write APIs.

**Utility**
- `uvx vhecfsck demo` runs on a clean machine with no database and no data, and visibly
  reproduces a recall collapse.
- The tool detects the degradation in the `lance#4164` reproduction scenario and exits `2`
  while the engine's own health signals stay green.
- A CI pipeline can gate on it: documented exit codes, stable JSON, no interactive prompts,
  bounded runtime via `--max-seconds`.

**Quality**
- `make verify` (lint, format, strict type check, tests, coverage) is green on every commit.
- ≥90% line coverage on `vhecfsck/core/`, ≥80% overall.
- 1M × 768 audit completes within the published performance budget on the reference
  machine, with the measured number in the README rather than a vague claim.

## 7. Non-negotiable invariants

Any ticket that breaks one of these is wrong, no matter how green its tests are.

1. **Read-only.** No write path to any target, ever.
2. **No metric logic outside `core/`.** Adapters fetch data; front ends render reports.
3. **No silent passes.** A metric that could not be computed reports `UNAVAILABLE` and is
   never rendered as a healthy value.
4. **Deterministic given a seed.** Same input plus same seed equals same report, bit for bit.
5. **Every optimised path has a naive oracle** in the test suite.
6. **No credentials or personal data in reports, logs, or scene payloads.** Connection
   strings are redacted; vector payloads and raw text are never exported.
7. **No network egress except to the audited target.** No telemetry, no update checks.
