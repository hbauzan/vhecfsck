# P10 — Post-1.0 Horizon

**Status:** deliberately unplanned.

This file exists so that good ideas arriving mid-project have somewhere to go other than into
the current phase. Nothing here has tickets, acceptance criteria, or a commitment. Detailed
planning happens only after `v0.1.0` has real users, because their reports will reorder this
list in ways that are impossible to predict now.

The single most likely error at this stage is pulling one of these items forward into the MVP
because it is interesting. Each entry therefore records what it is genuinely blocked on.

---

## Candidate directions

### More engines
Weaviate (the [`#11951`](https://github.com/weaviate/weaviate/issues/11951) entry-point
pathology is the most visceral failure in the whole anchor set and deserves an adapter),
Milvus, Elasticsearch / OpenSearch kNN, Chroma, Vespa, Turbopuffer, raw FAISS index files.

*Blocked on:* demand signal. Each adapter is a maintenance obligation forever, and the
capability matrix is only credible if every row in it is actually tested. Better to have three
well-tested engines than eight aspirational ones.

### Graph-level diagnostics
Full HNSW traversal analysis: in-degree distribution, unreachable-node fraction, layer
occupancy, entry-point reachability under tombstones. This would move the tool from inferring
path blocking via tombstone ratios to measuring it directly — a genuine step up in diagnostic
power.

*Blocked on:* engines exposing graph structure through a read-only interface. P7-06 will
establish what is actually obtainable; if the answer is "nothing", this requires reading index
files directly per engine, which is a large and version-fragile undertaking.

### Historical trending
Persist reports over time and detect drift before a threshold is crossed. The natural
successor to baseline mode, and arguably where the real value lies: a slow slide from 0.97 to
0.88 is more useful to catch than the moment it crosses 0.85.

*Blocked on:* a storage decision. Introducing a database into a tool whose main selling point
is that it has no moving parts needs care. Likely answer: append-only files plus Prometheus,
not a database.

### Remediation advisor (`--advise`)
Print the exact command a human could run: `VACUUM ANALYZE`, index rebuild with a suggested
`num_partitions`, recommended `ef_search` given the measured recall curve.

*Constraint, permanent:* the tool prints; the operator runs. Executing remediation would
violate the read-only invariant and is out of scope forever, not merely deferred.

### Recall-versus-effort curves
Sweep `nprobe` / `ef_search` and publish the recall-latency frontier, turning a pass/fail into
a tuning recommendation. Probably the single most requested feature once people start using
the tool, because it answers "what should I set it to?" rather than only "is it broken?".

*Blocked on:* runtime cost. A sweep multiplies audit duration by the number of points, though
ground truth is computed once and reused, which makes it cheaper than it first appears.

### Embedding-model diagnostics
Intrinsic dimensionality estimation, cluster structure quality, duplicate and near-duplicate
detection, dimension collapse. Adjacent and valuable, and the hubness machinery already exists.

*Risk:* scope drift into "embedding quality evaluation", which
[`00-vision-and-scope.md §5`](../00-vision-and-scope.md) explicitly excludes. If pursued, it
should probably be a sibling tool sharing `core/`, not a growth of this one.

### Query-log-driven auditing
Ingest real query logs, weight recall by query frequency, identify which production queries are
most damaged. The strongest possible evidence class, since it measures what users actually
experience rather than what a sampled corpus suggests.

*Blocked on:* a log format decision and the privacy implications of handling real query
embeddings.

### Kubernetes-native operation
A sidecar or operator, a CRD for scheduled audits, native Prometheus service discovery.

*Blocked on:* evidence that anyone wants it. A `CronJob` plus the textfile collector already
covers the use case, and shipping an operator that nobody asked for is a classic
infrastructure-tooling misstep.

### GPU-accelerated ground truth
CuPy or Torch backend to lift the single-node ceiling well above 1M vectors.

*Blocked on:* demand above the current ceiling, and a way to test it in CI. Note that this
changes the numerical guarantees: GPU reduction order differs, so bit-identical determinism
across backends would no longer hold and the determinism invariant would need restating.

### Distributed / sampled auditing at very large scale
Above roughly 10M vectors, exact ground truth stops being reasonable on one node. The honest
answer is sampling with a published confidence interval — the bootstrap machinery from P2-05
already provides the statistical shape.

*Blocked on:* someone with a 100M-vector index and a real need.

### `smartctl`-style predictive health
Aggregate metrics into a single health score with a trend, in the spirit of the `smartctl`
analogy that motivates the project.

*Risk:* a composite score invented without evidence is exactly the kind of unjustifiable
number [`00-vision-and-scope.md §2.2`](../00-vision-and-scope.md) rules out. Only worth doing
if calibration data across many real indexes eventually justifies a weighting — which is to
say, not for a long time.

---

## Explicitly and permanently out of scope

Restated here because these will be requested, repeatedly, and a consistent answer is worth
more than a case-by-case one.

- **Writing to, repairing, or optimising any index.** The read-only invariant is the product.
- **Sitting in the query path.** Not a proxy, not middleware.
- **Hosted SaaS, accounts, or telemetry of any kind.** No phone-home, ever.
- **Being a vector database.**
