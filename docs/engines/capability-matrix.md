# Consolidated Engine Capability & Metric Matrix

This document provides a single consolidated matrix of target engines versus metrics, detailing exactness, evidence ceilings, and provenance per [ADR-0013](../../roadmap/adr/0013-adapter-protocol.md).

---

## Metric Support Matrix by Engine

| Metric / Feature | Synthetic | LanceDB | Qdrant | PostgreSQL / pgvector |
| :--- | :--- | :--- | :--- | :--- |
| **Index Row / Vector Counts** | `OK` (Exact) | `OK` (Exact) | `OK` (Exact / Telemetry) | `OK` (Proxy / Estimated) |
| **Deletion Fraction (DFI)** | `OK` (Exact) | `OK` (Exact) | `OK` (Exact / Telemetry)* | `OK` (Proxy, Table `n_dead_tup`) |
| **Canary Recall (k-NN)** | `OK` (Exact) | `OK` (Exact, `float16` upcast) | `OK` (Exact, `hnsw_ef`) | `OK` (Exact, `EXPLAIN` guarded) |
| **IVF Partition CV** | `OK` (Exact) | `OK` (Exact) | `UNAVAILABLE` (HNSW) | `UNAVAILABLE` |
| **HNSW Graph Stats** | `UNAVAILABLE` | `UNAVAILABLE` (IVF) | `UNAVAILABLE` (Telemetry gap) | `UNAVAILABLE` (SQL gap) |
| **Filtered Search** | `False` | `False` | `True`** | `False` |
| **Custom Search Parameters** | `OK` (`ef_search`, `nprobe`) | `OK` (`nprobes`) | `OK` (`hnsw_ef`) | `OK` (`hnsw.ef_search`, `ivfflat.probes`) |

> **\*** Note on Qdrant DFI: Derived strictly from per-segment `num_deleted_vectors` telemetry. If segment telemetry is omitted by the server, DFI is reported as `UNAVAILABLE` rather than substituting `points_count - indexed_vectors_count` (which misreports unindexed vectors as deleted).
>
> **\*\*** Note on Filtered Search: Supported for Qdrant via Schema 1.1 per-tenant / grouped canary recall (`canary_groups`, P7-03). Other engines remain `False`.

---

## Engine Detail Summaries & Guides

- **Synthetic Adapter**: Memory-backed reference engine used in unit/property tests. Exposes exact partition and deletion parameters with zero network/file I/O.
- **LanceDB Guide**: [docs/engines/lancedb.md](lancedb.md) — Columnar PyArrow-based snapshot audits (`--dataset-version N`), exact fragment metadata, exact DFI, and IVF cell statistics.
- **Qdrant Guide**: [docs/engines/qdrant.md](qdrant.md) — HTTP/gRPC collection audits, segment telemetry deleted counts, exact canary recall, `hnsw_ef` parameter configuration.
- **Postgres / pgvector Guide**: [docs/engines/pgvector.md](pgvector.md) — Catalog introspection, `n_dead_tup` table-level DFI proxy (capped at `MEDIUM` evidence), `EXPLAIN` sequential-scan guard, read-only session isolation (`default_transaction_read_only=on`).
- **HNSW Graph Statistics Findings**: [docs/engines/graph-stats.md](graph-stats.md) — Detailed investigation recording why HNSW internal topology statistics conclude as `UNAVAILABLE` for both Qdrant and pgvector under pinned versions.
