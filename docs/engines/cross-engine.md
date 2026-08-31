# Cross-engine consistency

Same `SeedSpec`, same seed, same vectors, same deletions, four adapters.
Intrinsic metrics (hub share, anti-hub fraction) are properties of the
embedding space: they must agree. Engine-dependent metrics (canary recall,
DFI) are allowed a documented range.

Automated test: `tests/integration/test_cross_engine.py`.

## Regenerating the table

```bash
uv sync --group dev --extra lancedb --extra qdrant --extra postgres
uv run pytest tests/integration/test_cross_engine.py -q --no-cov -s
```

Do not use `--all-extras`. After the run, restore the gate venv with
`uv sync --group dev --extra lancedb` before `make verify`.

## Corpus

`SeedSpec`: n=1024, dim=16, L2, seed=2026, HNSW m=16 / `ef_construction=64`,
16 deletes, 0 updates, 4 clusters, `n_tenants=0` (defaults). Live set = 1008.
Hubness sample size 2048 so every live id is a query (`|S| ≥ 1000`, ADR-0006).
Search knobs: `ef_search=64`, `nprobe=8`.

Pinned: `qdrant/qdrant:v1.19.0`, `pgvector/pgvector:0.8.6-pg16`, LanceDB extra
as in `pyproject.toml`.

## Measured table

Machine: local Docker + in-process synthetic/Lance. One run of the command
above.

| engine | hub_share | antihub | recall_dist | DFI |
| :--- | ---: | ---: | ---: | ---: |
| synthetic | 0.0550 | 0.0496 | 0.9000 | 0.0156 |
| lancedb | 0.0550 | 0.0496 | 0.9000 | 0.0156 |
| qdrant | 0.0550 | 0.0496 | 0.9000 | UNAVAILABLE |
| pgvector | 0.0550 | 0.0496 | UNAVAILABLE | 0.0156 |

Unrounded hub share: `0.05496031746031746`. Unrounded anti-hub:
`0.0496031746031746`. Identical across all four engines (delta 0, well inside
the 2% band). That is enumeration + L2 vectors agreeing, not a coincidence of
thresholds.

## Engine-dependent range

| Metric | Range on this corpus | Notes |
| :--- | :--- | :--- |
| canary `recall_dist` | 0.90 or `UNAVAILABLE` | 0.90 is self-exclusion padding (`k` hits include the query id). pgvector: planner sequential-scans n=1024 (P7-04 `index_not_used`); not a hubness disagreement. |
| DFI | 0.0156 (= 16/1024) or `UNAVAILABLE` | Synthetic, LanceDB, and pgvector (table-level proxy) match the deletion fraction. Qdrant DFI stays `UNAVAILABLE` when per-segment `num_deleted_vectors` is missing (metrics spec §4.2; never the `indexed_vectors_count` trap). |

This page is not the capability matrix (`docs/engines/capability-matrix.md`).
