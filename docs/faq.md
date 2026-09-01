# Frequently Asked Questions (FAQ)

---

## Security & Data Safety

### 1. How do I know `vhecfsck` will not touch or corrupt my production database?
`vhecfsck` is built under a non-negotiable **Strictly Read-Only Guarantee** ([ADR-0001](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/adr/0001-read-only-by-default.md)).
- The adapter protocol (`vhecfsck/adapters/base.py`) has zero write, mutate, delete, or compaction methods.
- Database connections force read-only sessions (`default_transaction_read_only = on` for PostgreSQL, read-only file handles for LanceDB).
- Integration test suites verify zero state mutations using hash/mtime snapshot comparisons ([`DirectorySnapshot`](https://github.com/hbauzan/vhecfsck/blob/main/docs/read-only.md)) and execution against read-only mounts (`chmod -R a-w`).

### 2. Does `vhecfsck` transmit index data, telemetry, or metrics to external servers?
No. `vhecfsck` is **100% offline with zero network egress**. Automated integration test suites ([`tests/integration/test_readonly_all.py`](https://github.com/hbauzan/vhecfsck/blob/main/docs/read-only.md)) assert zero outbound socket connections during audit execution.

---

## Calibration & Thresholds

### 3. Where do the default metric thresholds come from?
Thresholds are derived from empirical measurements across isotropic Gaussian control datasets across dimensions $d \in \{16, 64, 128, 384, 768, 1536\}$ and public ANN benchmark datasets ([`docs/calibration/thresholds.md`](calibration/thresholds.md)).
Default profiles adapt dynamically to vector dimensionality (`low`, `medium`, `high`, `ultra_high`) while allowing explicit overrides via CLI parameters or configuration files.

### 4. What should I do if I get a false positive audit verdict?
If your index returns a `WARN` or `FAIL` verdict on a known-healthy production collection, submit a report using the [False Positive Issue Template](https://github.com/hbauzan/vhecfsck/issues/new?template=false_positive_report.md). Include vector dimension $d$, metric space, total vector count $N$, and reported values so we can calibrate future profiles.

---

## Diagnostics & Architecture

### 5. Why does my vector database pass `/healthz` probes while serving incorrect results?
Relational databases degrade by consuming more I/O latency, but return correct rows. Vector indexes degrade by **altering topological retrieval**.
When nodes are deleted in HNSW or appends occur without IVF re-indexing, beam search (`ef_search`) spends its candidate budget on tombstoned or unindexed vectors. The engine filters dead candidates post-search and returns a short or empty payload (`200 OK`) while liveness probes remain green.

### 6. How does `vhecfsck` compute canary recall without pre-labeled ground truth?
`vhecfsck` draws a random sample of $Q$ vectors from your collection as queries, computes exact brute-force nearest neighbours ($\mathcal{O}(N)$ oracle) in memory, and compares exact nearest-neighbour sets against the engine's approximate nearest-neighbour (ANN) response.
