# ADR-0016 — Optional extras for Qdrant and Postgres / pgvector

**Status:** Accepted
**Affects:** P7, packaging (`pyproject.toml`)

## Context

ADR-0002 keeps the base install lean: engine SDKs are extras, imported lazily
inside adapter factories. P0 declared empty `qdrant` and `postgres` extras.
P7 implements those adapters, so the extras must name real, pinned packages.

Qdrant is an HTTP/gRPC server **and** ships an in-process local client
(`QdrantClient(":memory:")` / `path=`). Postgres / pgvector is a live SQL
server; the adapter must connect read-only (ADR-0001) without pulling SQLAlchemy
or a second driver.

Guardrail 2: a new dependency needs an ADR, including optional extras.

## Decision

- **`[qdrant]`** extra: `qdrant-client>=1.12.0,<2`. That range includes
  `query_points`, local/embedded mode, and gRPC-optional HTTP. Do not pull the
  `fastembed` extra — it is unrelated to auditing an existing collection.
- **`[postgres]`** extra: `psycopg[binary]>=3.2` plus `pgvector>=0.3`.
  `psycopg` 3 is the current PostgreSQL driver; the `[binary]` extra avoids a
  libpq compile at install time. `pgvector` registers the `vector` type so
  reads and `ORDER BY` distance operators round-trip as arrays, not text.
- Both extras stay **opt-in**. Default `uv sync` / CI `uv sync --group dev`
  does not install them (lesson 5). Tests that need the SDK use
  `@pytest.mark.requires_qdrant` / `@pytest.mark.requires_postgres` or
  `pytest.importorskip`.
- Adapters accept an injected client/connection so unit tests can exercise
  the read path without the extra installed. Production `open_target` still
  constructs the SDK lazily.

## Consequences

**Buys:** `pip install "vhecfsck[qdrant]"` / `"vhecfsck[postgres]"` is a real
install; missing extras still produce the P1-06 hint rather than a traceback.
Local Qdrant tests can run without Docker.

**Costs:**
- `qdrant-client` brings grpcio/httpx/pydantic (already in base) and a numpy
  upper bound that must stay compatible with the base `numpy>=1.26` pin.
- `psycopg[binary]` is a platform wheel; exotic architectures fall back to
  source builds.
- Default `make verify` does not install extras. Adapter line coverage in the
  gate comes from injected-client unit tests, not from a live server.

## Alternatives considered

- **`testcontainers` in the product extra.** Rejected for this ticket: it is a
  test harness, not an audit dependency. P7-01 may add it under the `dev`
  group later; that is a separate ADR.
- **SQLAlchemy.** Rejected: a second query layer on a read-only SELECT path,
  and more surface for the AST write guard to misread.
- **`psycopg2`.** Rejected: psycopg 3 is the maintained driver and exposes
  `Connection.read_only` plus `Cursor.stream` (so adapters never call
  `.execute()`, which `scripts/check_readonly.py` denies).
- **Putting engine SDKs in the base install.** Rejected by ADR-0002.

## Revisit if

- `qdrant-client` 2.x ships a breaking local-mode or `query_points` change.
- psycopg drops `Cursor.stream` or `Connection.read_only`.
- The numpy upper bound from `qdrant-client` conflicts with a base numpy bump.
