# Glossary

Terms used throughout this roadmap. Definitions are scoped to how the term is used in this
project, which occasionally differs from broader usage — where that happens, the difference is
noted, because an implementer relying on the general meaning would get it wrong.

---

### ANN — Approximate Nearest Neighbour
Search that trades exactness for speed. Every index this tool audits is an ANN index; the entire
premise is that the approximation degrades over time in ways nobody measures.

### Anti-hub
An indexed vector that is never returned as anyone's nearest neighbour (`N_k = 0`). Operationally:
content that exists in the index, was paid for in storage and embedding cost, and is functionally
invisible to search. The mirror image of a hub.

### Beam search
The traversal strategy HNSW uses at query time: maintain a candidate set of size `ef_search`,
repeatedly expand the closest unexplored candidate. The mechanism matters here because tombstoned
nodes consume beam budget before being filtered out — see *path blocking*.

### Canary recall
This project's headline metric: the fraction of true nearest neighbours the index actually returns,
measured against exact brute-force ground truth. "Canary" because it is a small, cheap, periodic
probe whose failure indicates something larger is wrong. Defined in
[`02-metrics-spec.md §2`](02-metrics-spec.md).

### Capability
A boolean declaration by an adapter that a particular read is supported. Defaults to `False`, so a
forgotten declaration degrades a metric to `UNAVAILABLE` rather than producing a wrong number. See
[ADR-0013](adr/0013-adapter-protocol.md).

### Centroid drift
When data is inserted into an IVF index without retraining the k-means centroids, the centroids no
longer represent the data distribution. New vectors land unevenly, partitions become imbalanced,
and queries probe cells that no longer contain their true neighbours. The mechanism behind
[`lance#4164`](https://github.com/lancedb/lance/issues/4164).

### CV — Coefficient of Variation
Standard deviation divided by the mean. Used for partition size imbalance because it is
scale-free: doubling every partition's size leaves it unchanged. **This project uses population
standard deviation (`ddof = 0`)**, which is normative — partitions are the entire population, not
a sample.

### Dead tuple
PostgreSQL's term for a row version that is no longer visible to any transaction but has not yet
been reclaimed by `VACUUM`. In a pgvector HNSW index, dead tuples are traversed and then filtered,
producing the same path-blocking effect as tombstones. The mechanism behind
[`pgvector#244`](https://github.com/pgvector/pgvector/issues/244).

### DFI — Deletion Fragmentation Index
`dead / (live + dead)` over the navigable population. This project's measure of how much of an
index consists of entities the search will traverse but never return. Defined in
[`02-metrics-spec.md §4`](02-metrics-spec.md).

### Distance concentration
In high dimensions, the variance of pairwise distances shrinks relative to their mean — every point
becomes roughly equidistant from every other. The root cause of hubness, and the reason
nearest-neighbour search gets structurally harder as embedding dimension grows.

### `ef_search`
HNSW's query-time exploration budget: how many candidates the beam search keeps. Higher means
better recall and higher latency. Critically, tombstoned nodes consume this budget, so a fixed
`ef_search` delivers progressively worse recall as an index accumulates deletions.

### Evidence strength
`high` / `medium` / `low` — this project's self-assessment of how much a metric's sample supports
its conclusion. A `low`-evidence metric may never produce a `FAIL` verdict on its own. Exists
because a recall figure from 200 corpus-drawn queries and one from 50,000 production queries are
not the same claim.

### Ground truth
The exact `k` nearest neighbours, computed by brute-force distance calculation over the entire live
corpus. The oracle everything else is measured against. If it is wrong, everything is wrong — hence
[ADR-0005](adr/0005-ground-truth-precision-and-blocking.md).

### Hub
A vector that appears in the top-`k` results of a disproportionate number of unrelated queries.
Hubs sit at topological crossroads in high-dimensional space and cannibalise retrieval slots. Not
an engine bug — a property of the embedding space, which is why no engine reports it.

### Hubness
The phenomenon of the `N_k` distribution becoming severely skewed as dimensionality rises. Measured
here by *top-1% hub share* and *anti-hub fraction*, using the self-queried sampling regime of
[ADR-0006](adr/0006-hubness-sampling-regime.md).

### HNSW — Hierarchical Navigable Small World
A layered proximity-graph index. Fast and accurate, but edges are expensive to rewire, so deletes
are handled by tombstoning rather than by repairing the graph. That trade-off is the source of
path blocking.

### IVF — Inverted File Index
Partitions the vector space into `K` Voronoi cells by k-means at build time; a query scans only the
`nprobe` cells nearest to it. Fast when partitions are balanced and centroids represent the data;
degrades toward a sequential scan when they do not.

### `N_k(x)`
The number of times vector `x` appears in the `k`-nearest-neighbour list of other vectors. The
fundamental quantity behind every hubness metric. `sum(N_k) == S · k` is an exact invariant and is
asserted in code — a violation means every hubness number is wrong.

### `nprobe`
IVF's query-time parameter: how many partitions to scan. Higher means better recall and higher
latency. Any recall figure reported without its `nprobe` is uninterpretable, which is why the
effective value is always echoed into the report.

### Path blocking
This project's term for the specific failure where beam search spends its budget on tombstoned
nodes and returns fewer results than requested — or none — despite live, valid neighbours existing
nearby. The mechanism connecting tombstones to recall collapse. Its signature in a report is a
non-zero `detail.returned_invalid`, which is often more diagnostic than the recall number itself.

### PQ — Product Quantisation
Compresses vectors by splitting them into sub-vectors and replacing each with a codebook index.
Saves memory, loses precision, and manufactures distance ties in bulk — which is why recall must be
tie-tolerant ([ADR-0007](adr/0007-tie-tolerant-recall.md)) and why engine-reported distances can
never be trusted for scoring.

### RAG — Retrieval-Augmented Generation
The dominant application pattern for vector search: retrieve relevant documents, feed them to a
language model. Relevant here because retrieval degradation surfaces as vague, subtly-wrong model
output rather than as an error, making it exceptionally hard to attribute.

### Recall@k
Fraction of the true top-`k` that a search actually returned. This project reports two variants:
`recall_id` (strict ID set intersection) and `recall_dist` (tie-tolerant, distance-thresholded).
`recall_dist` is the gated value.

### Read-only
In this project, a load-bearing technical guarantee rather than a description: enforced at five
independent layers and verified empirically. See [ADR-0001](adr/0001-read-only-by-default.md).

### Recall boundary (`d_K`)
The true distance from a query to its `K`-th ground-truth neighbour. Used as the threshold for
tie-tolerant recall: any returned vector at least as close as `d_K` counts as a hit, regardless of
its ID.

### Segment
Qdrant's unit of storage. Deleted vectors are tracked per segment, which is why exact DFI requires
segment-level telemetry — and why the convenient collection-level ratio
(`points_count` vs `indexed_vectors_count`) is **not** a fragmentation measure: it also excludes
vectors in segments below the indexing threshold.

### Tombstone
A marker indicating a vector has been logically deleted but remains physically present in the
index. Cheap to create, and the reason deletion silently degrades recall in graph indexes.
Weaviate and Qdrant use the term directly; PostgreSQL's equivalent is the dead tuple.

### `UNAVAILABLE`
A metric state meaning "could not be computed", carrying a reason and never a value. Deliberately
distinct from `OK` in every output format, because an engine that cannot report deleted counts must
not score a perfect DFI of zero. See
[ADR-0004](adr/0004-metric-result-states-and-exit-codes.md).

### Verdict
The aggregate result of an audit: `OK`, `WARN`, `FAIL`, or `INCONCLUSIVE`. Maps to the process exit
code. Computed as the worst state among enabled metrics, with `low`-evidence metrics capped at
`WARN`.

### Voronoi cell
The region of space closer to one IVF centroid than to any other — in other words, one IVF
partition. Cell size imbalance is what *partition size CV* measures.
