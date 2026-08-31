# PostgreSQL / pgvector Engine Guide

`vhecfsck` provides a native, read-only adapter for auditing **PostgreSQL** tables equipped with the **pgvector** extension.

---

## Quickstart

Install the Postgres engine extra using `uv` (do **not** use `pip` or `--all-extras`):

```bash
uv sync --extra postgres
```

Audit a pgvector table over PostgreSQL:

```bash
# Audit a pgvector table via DSN
vhecfsck audit postgresql://auditor:secret@localhost:5432/dbname?table=items&vector_column=embedding

# Audit specifying custom HNSW search effort parameter
vhecfsck audit postgresql://auditor:secret@localhost:5432/dbname?table=items&vector_column=embedding&hnsw_ef_search=64
```

---

## Required Privileges & Recommended Read-Only Role

`vhecfsck` connects strictly in read-only mode, backed by PostgreSQL transaction controls and privilege isolation.

### Recommended `SELECT`-Only Role Setup

In production PostgreSQL databases, create a dedicated read-only role with access restricted to the audited table and system catalogs:

```sql
-- Create auditor role
CREATE ROLE vhecfsck_auditor WITH LOGIN PASSWORD 'strong_password';

-- Grant connection to database
GRANT CONNECT ON DATABASE dbname TO vhecfsck_auditor;

-- Grant SELECT on target schema and table
GRANT USAGE ON SCHEMA public TO vhecfsck_auditor;
GRANT SELECT ON TABLE items TO vhecfsck_auditor;
```

### Server-Enforced Read-Only Session Isolation

Defence-in-depth is enforced at the database driver level:
1. Every audit connection sets `options="-c default_transaction_read_only=on"`.
2. Connection handles set `Connection.read_only = True`.
3. Queries execute inside explicit `READ ONLY` transactions.
4. If connected using a PostgreSQL superuser role, `vhecfsck` issues a one-time warning recommending role privilege demotion.

---

## Version Compatibility Matrix

`vhecfsck` tests and supports the following version bounds for PostgreSQL and pgvector:

| Component / Driver | Tested Version Range | Extra Specification |
| :--- | :--- | :--- |
| `psycopg` (v3 binary) | `>=3.2.0, <4.0.0` | `vhecfsck[postgres]` |
| `pgvector` Python SDK | `>=0.3.0, <1.0.0` | `vhecfsck[postgres]` |
| PostgreSQL Server | `16+` | Server requirement |
| `pgvector` Extension | `0.8.x` (and 0.7+) | Extension requirement |

---

## Catalog Introspection & Metric Provenance

`vhecfsck` introspects PostgreSQL system catalogs (`pg_class`, `pg_am`, `pg_index`, `pg_attribute`, `pg_opclass`) to determine vector column dimension, distance metric space (`vector_l2_ops`, `vector_cosine_ops`, `vector_ip_ops`), and index build parameters (`m`, `ef_construction`, `lists`).

| Metric | Support State | Exact / Proxy | Evidence Level | Notes & Provenance |
| :--- | :--- | :--- | :--- | :--- |
| **Index Counts** | `OK` | **Proxy / Estimated** | `MEDIUM` | Derived from `pg_stat_user_tables` (`n_live_tup`, `n_dead_tup`). |
| **Deletion Fraction (DFI)** | `OK` | **Proxy / Estimated** | `MEDIUM` | Table-level dead tuple count (`n_dead_tup`). Flagged `proxy=True`, evidence capped at `MEDIUM`. |
| **Canary Recall** | `OK` | **Exact** | `HIGH` | Native k-NN query vs blocked ground truth. Search effort tuned via `SET LOCAL hnsw.ef_search` or `SET LOCAL ivfflat.probes`. |
| **IVF Partition CV** | `UNAVAILABLE` | N/A | `UNAVAILABLE` | Index cell distribution counts are not SQL-accessible for IVFFlat in pgvector system stats. |
| **HNSW Graph Stats** | `UNAVAILABLE` | N/A | `UNAVAILABLE` | pgvector internal graph entry points and node in-degree histograms are not exposed via SQL. Cites [docs/engines/graph-stats.md](graph-stats.md). |
| **Filtered Search** | `False` | N/A | N/A | Filtered search capability is `False` in current release. |

### `EXPLAIN` Guard Against Sequential Scans

To prevent reporting meaningless perfect recall (`1.0`) when PostgreSQL query planner opts for a full sequential scan (e.g., on small tables or default planner settings), `vhecfsck` executes `EXPLAIN` on test queries before running canary recall. If `EXPLAIN` shows a sequential scan instead of index scan, canary recall is reported as `UNAVAILABLE(index_not_used)`.

---

## Read-Only Invariant & Security Verification

- **Driver Streaming**: Queries use `Cursor.stream` to read batch rows without buffer allocation overhead or write side-effects.
- **AST Write Guard**: `scripts/check_readonly.py` denies mutator SQL keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `VACUUM`, `REINDEX`).
- **Session Enforcement**: PostgreSQL rejects any write statement attempting execution within `default_transaction_read_only=on`.
