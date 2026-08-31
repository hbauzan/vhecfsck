# Qdrant Engine Guide

`vhecfsck` provides a native, read-only adapter for auditing **Qdrant** vector database collections over HTTP or gRPC.

---

## Quickstart

Install the Qdrant engine extra using `uv` (do **not** use `pip` or `--all-extras`):

```bash
uv sync --extra qdrant
```

Audit a Qdrant collection over HTTP or gRPC:

```bash
# Audit a collection via HTTP DSN
vhecfsck audit qdrant+http://localhost:6333/my_collection

# Audit via gRPC endpoint
vhecfsck audit qdrant+grpc://localhost:6334/my_collection

# Audit with explicit API key parameter
vhecfsck audit qdrant+https://cluster.qdrant.io:6333/my_collection?api_key=SECRET
```

---

## Required Privileges & Recommended Read-Only Role

`vhecfsck` strictly performs read-only introspection and search queries.

- **API Keys / Access Control**: When using Qdrant Cloud or RBAC-enabled deployments, configure a read-only API key with `read` permissions restricted to the target collection.
- **Allowed Operations**: The adapter accesses only read-shaped REST and gRPC endpoints:
  - `GET /collections/{collection_name}` (collection schema and telemetry)
  - `GET /telemetry` (segment-level deletion accounting)
  - `POST /collections/{collection_name}/points/scroll` (vector enumeration)
  - `POST /collections/{collection_name}/points` (point retrieval by ID)
  - `POST /collections/{collection_name}/points/search` or query endpoints (k-NN canary search)
- **Deny Mutating Endpoints**: The adapter never issues `PUT`, `DELETE`, or index creation / mutation requests.

---

## Version Compatibility Matrix

`vhecfsck` tests and supports the following version bounds for Qdrant:

| Package / Component | Tested Version Range | Extra Specification |
| :--- | :--- | :--- |
| `qdrant-client` | `>=1.12.0, <2.0.0` | `vhecfsck[qdrant]` |
| Qdrant Server | `v1.19.0` (and 1.x line) | N/A (Docker container pinned) |

If runtime versions fall outside the tested window, `vhecfsck` emits a warning without aborting the audit.

---

## Metric Provenance & Honest Capability Matrix

`vhecfsck` exposes explicit capability flags for Qdrant. If telemetry or exact counts are missing, metrics gracefully degrade to `UNAVAILABLE` per [ADR-0013](capability-matrix.md).

| Metric | Support State | Exact / Proxy | Notes & Provenance |
| :--- | :--- | :--- | :--- |
| **Index Counts** | `OK` | **Exact** | Derived from `/telemetry` per-segment data or count API. |
| **Deletion Fraction (DFI)** | `OK` / `UNAVAILABLE` | **Exact** | Uses per-segment `num_deleted_vectors` telemetry. If segment telemetry is missing, DFI is `UNAVAILABLE`. |
| **Canary Recall** | `OK` | **Exact** | Evaluates native k-NN search against exact ground truth; honors `hnsw_ef`. |
| **IVF Partition CV** | `UNAVAILABLE` | N/A | Qdrant uses HNSW indexing (IVF statistics do not apply). |
| **HNSW Graph Stats** | `UNAVAILABLE` | N/A | Qdrant REST/gRPC APIs do not expose internal graph entry points or node in-degrees. Cites [docs/engines/graph-stats.md](graph-stats.md). |
| **Filtered Search** | `False` | N/A | Per-tenant/filtered canary search is `False` in the current adapter version (future ticket P7-03 may introduce grouped canary filtering). |

### The Telemetry Trap: Why `points_count` vs `indexed_vectors_count` is NOT Used for DFI

A tempting alternative for computing deletion fraction is comparing `points_count` to `indexed_vectors_count`. **`vhecfsck` explicitly avoids this ratio** (see [ADR-0013](https://github.com/hbauzan/vhecfsck/blob/main/roadmap/adr/0013-adapter-protocol.md) and metrics spec §4.2):

1. `indexed_vectors_count` excludes vectors in small or unindexed segments below Qdrant's indexing threshold (`indexing_threshold`).
2. On a freshly loaded, clean collection, unindexed vectors would cause `points_count - indexed_vectors_count` to report spurious non-zero deletion fragmentation.
3. Therefore, `vhecfsck` derives DFI **only** from explicit per-segment `num_deleted_vectors` telemetry. If this telemetry is unobtainable from the server version, DFI is marked `UNAVAILABLE` rather than substituting a misleading proxy.

---

## Read-Only Invariant & Security Verification

- **Read-Only API Calls Only**: Zero mutating HTTP methods or gRPC write requests are issued.
- **AST Write Guard**: Enforced via `scripts/check_readonly.py` during `make verify`.
- **Target Invariance**: Audit runs leave Qdrant collection vectors, point counts, and segment structures unchanged.
