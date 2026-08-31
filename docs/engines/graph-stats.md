# HNSW Graph Statistics — Engine Availability & Findings

This document records the investigation into HNSW graph introspection across vector database engines for ticket P7-06.

---

## Overview

Ticket P7-06 evaluated whether target vector engines expose read-only introspection APIs for HNSW graph structure—specifically:
- In-degree histogram across graph nodes
- Graph entry point vector IDs
- `entrypoint_tombstoned` status (whether the entry point node has been deleted/tombstoned)

Per ADR-0013 and Guardrail 3 (`UNAVAILABLE` > comfortable guess), if an engine does not expose these structural properties, `Capabilities.report_graph_stats` remains `False`, `adapter.graph_stats()` returns `None`, and no unrelated proxy metric is substituted.

---

## 1. Qdrant

- **Engine version evaluated:** Qdrant v1.19.0 (`qdrant-client` 1.12+)
- **APIs inspected:** Collection telemetry endpoints (`/telemetry`), collection info (`/collections/{name}`), REST points API, and gRPC endpoints.
- **Finding:** Qdrant collection telemetry exposes segment-level `num_deleted_vectors` and `num_vectors` (used for DFI). However, Qdrant's public REST and gRPC interfaces do not expose HNSW internal graph topology, entry point vector IDs, in-degree distributions, or entrypoint tombstone status.
- **Result:** `report_graph_stats = False`, `graph_stats() -> None`.

---

## 2. PostgreSQL / pgvector

- **Engine version evaluated:** pgvector 0.8.x on PostgreSQL 16+
- **APIs inspected:** Catalog tables (`pg_class`, `pg_am`, `pg_index`, `pg_attribute`, `pg_opclass`), stats views (`pg_stat_user_tables`), and extension functions (`pgstattuple`).
- **Finding:** pgvector constructs standard PostgreSQL index relation files for HNSW (`amname = 'hnsw'`). PostgreSQL system catalogs and pgvector SQL interfaces expose index build options (`m`, `ef_construction`) and operational knobs (`hnsw.ef_search`, `hnsw.iterative_scan`), but provide no SQL-accessible view or function to inspect internal graph entry points, node in-degree histograms, or entrypoint tombstone status.
- **Result:** `report_graph_stats = False`, `graph_stats() -> None`.

---

## 3. LanceDB

- **Engine version evaluated:** LanceDB 0.37+ / Lance 0.11+
- **Finding:** LanceDB uses IVF-PQ partition indexing rather than HNSW. Graph statistics are `N/A` for IVF indexes (documented in `docs/engines/lancedb.md`).

---

## Architectural Conclusion

Both primary HNSW target engines (Qdrant and pgvector) conclude as **not obtainable** for graph statistics under their pinned versions. The pipeline supports `entrypoint_tombstoned` escalation (escalating DFI state to `FAIL` if an adapter reports `entrypoint_tombstoned = True`), but when `graph_stats()` is `None`, DFI state evaluation proceeds strictly from deletion ratios without guessing.
