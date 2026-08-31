# Scenario Reproduction: qdrant#7147

Multitenant HNSW subgraphs (`m=0`, `payload_m>0`, payload index `is_tenant: true`)
can return healthy collection status while **filtered** search precision on one
tenant collapses. An unfiltered / aggregate canary can still look fine.

Upstream: [qdrant#7147](https://github.com/qdrant/qdrant/issues/7147)
(open; reporter: precision ~0.98 unfiltered vs ~0.61 filtered at v1.15.x, later
recurrence after heavy ingest). Pinned image: `qdrant/qdrant:v1.19.0`.

The automated test is `tests/integration/test_repro_qdrant_7147.py`. Writes live
in `tests/` (ADR-0001). `vhecfsck` never upserts, deletes, or rebuilds HNSW.

## Harness knobs

- Collection: n=480, dim=16, cosine, 8 tenants, `m=0`, `payload_m=32`,
  `ef_construction=64`, keyword payload index `tenant_id` with `is_tenant=true`.
- `indexing_threshold=10` and `hnsw.full_scan_threshold=10` so the planner
  cannot hide behind a brute-force scan of this small corpus.
- 48 deletes, 96 updates, then 4 extra full-live upsert rounds (segment churn).
- Canary: Q=40, K=10, `ef_search=64`.

## Measured numbers

Machine: local Docker, image above. One run (the test is deterministic at this
seed; ten-run flakiness was not observed because recall sat at ceiling).

| Probe | ID-recall@10 (self-excluded) | Empty result sets | `/healthz` |
| :--- | :--- | :--- | :--- |
| Unfiltered | 1.0000 | 0 / 40 | 2xx |
| Filtered by `tenant_id` | mean 1.0000, min 1.0000 | 0 / 40 | 2xx |

`vhecfsck audit` on the same target (`ef_search=64`, Q=40, canary+DFI only):

| Mode | canary `recall_dist` | canary state | `canary_groups` | verdict |
| :--- | :--- | :--- | :--- | :--- |
| Aggregate (no `--group-by`) | 0.90 | OK | `null` | INCONCLUSIVE (DFI UNAVAILABLE) |
| `--group-by tenant_id` | 0.90 headline | OK | t0–t7 all OK | INCONCLUSIVE (DFI UNAVAILABLE) |

Headline 0.90 is self-exclusion padding (`k` engine hits include the query id,
dropped to `-1`). Independent empty-result count is the engine signal.

## Pinned version: not reproduced

On `qdrant/qdrant:v1.19.0` this corpus does **not** reproduce the reporter's
filtered collapse (0.98 → 0.61). Filtered precision stayed 1.0 while `/healthz`
and collection status stayed green. The integration test remains a **regression
guard**: if a later image drops filtered min-recall below 0.70 while unfiltered
stays ≥ 0.80, it flags FAIL.

The product contrast (aggregate misses a dead tenant; grouped canary catches it)
is locked in `tests/unit/test_canary_groups.py` against a fake adapter that
returns the wrong tenant under filter. That test does not depend on Qdrant
still shipping the bug.

CLI: `--filter tenant_id=t0` (one group) and `--group-by tenant_id` (breakdown
in `canary_groups`, schema 1.1). Qdrant opts into `Capabilities.filtered_search`;
Postgres / LanceDB / synthetic stay `False` and ignore `--group-by` with a
warning.
