# Scenario Reproduction: pgvector#244

Dead tuples in an HNSW graph consume `ef_search` slots. Heap visibility then
filters them out, so the query returns short or empty result sets while the
table, the index, and the server all look healthy.

Upstream: [pgvector#244](https://github.com/pgvector/pgvector/issues/244)
(closed in 0.8.0 by iterative index scans). Pinned image:
`pgvector/pgvector:0.8.6-pg16`.

The automated test is `tests/integration/test_repro_pgvector_244.py`. Seeding
and `VACUUM` live in `tests/` (ADR-0001). `vhecfsck` never runs maintenance.

## Harness knobs

- Extra throwaway Postgres (not the session fixture). Autovacuum off on that
  table only.
- `ALTER DATABASE test SET enable_seqscan = off` so `EXPLAIN` uses HNSW. At
  2,500 × 16-d the planner still prefers a sequential scan (P7-04).
- Default `hnsw.iterative_scan = off` reproduces the collapse. `relaxed_order`
  mitigates it (see table). The audit connection inherits the server default
  (`off`).

## Measured numbers

Corpus: n=2500, dim=16, L2, HNSW m=16, `ef_construction=64`, 500 deletes, 2000
updates, then 6 extra full-live UPDATE rounds. Canary: Q=40, K=10,
`ef_search=10`. Machine: local Docker, image above.

| Stage | `hnsw.iterative_scan` | ID-recall@10 (self-excluded) | Empty result sets | `n_live_tup` | `n_dead_tup` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| After churn | `off` | 0.1025 | 12 / 40 | 2000 | 14500 |
| After churn | `relaxed_order` | 0.9000 | 0 / 40 | 2000 | 14500 |
| After operator `VACUUM` | `off` | 0.9000 | 0 / 40 | 2000 | 0 |

`vhecfsck audit` on the same target (`ef_search=10`, Q=40):

| Stage | canary `recall_dist` | canary state | `detail.short_returns` | `detail.returned_invalid` | DFI | verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| After churn | 0.13 | FAIL | 40 | 0 | 0.8788 | FAIL (exit 2) |
| After operator `VACUUM` | 0.90 | OK | 40 | 0 | 0.0 | (DFI recovered; canary recovered) |

`returned_invalid` stays 0: PostgreSQL heap visibility never returns a dead
tuple id. The smoking gun for this engine is short/empty result sets
(`short_returns` / independent empty count), not leaked tombstone ids.

`short_returns=40` after recovery is the canary self-exclusion pad (the query
id is stripped to `-1`). Independent empty counts (12 → 0) are the recovery
signal that does not include that pad.

## Remediation (operator, not `vhecfsck`)

`VACUUM` the table so HNSW can drop dead graph nodes. Iterative scans
(`hnsw.iterative_scan = relaxed_order`) are a query-time mitigation, not a
repair of the graph.
