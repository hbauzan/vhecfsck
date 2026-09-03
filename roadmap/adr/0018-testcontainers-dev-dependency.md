# ADR-0018 — testcontainers as a harness-only dev dependency

**Status:** Accepted
**Affects:** P7 (P7-01), packaging (`pyproject.toml`)

## Context

P7-01 needs disposable Qdrant and PostgreSQL+pgvector servers so later tickets
can reproduce engine pathologies without a human-provisioned DSN. The servers
are test infrastructure: they never ship in `uvx vhecfsck demo`.

ADR-0016 already rejected putting `testcontainers` in a product extra. Guardrail
2 requires an ADR for any new Python dependency, including harness libraries.
Lesson 5 forbids `uv sync --all-extras` in setup and CI.

## Decision

- Add **`testcontainers>=4.15,<5`** to `dependency-groups.dev` in
  `pyproject.toml`. It is not a project extra, not a runtime dependency, and
  not pulled by `uvx vhecfsck`.
- Default sync stays `uv sync --group dev`. Engine SDKs remain `[qdrant]` /
  `[postgres]` extras; seeding tests skip locally (actionable message) and
  **fail in CI** when an extra is missing.
- Image tags are pinned in `tests/integration/containers.py` (`qdrant/qdrant:v1.19.0`
  matching the locked `qdrant-client` 1.19 line, `pgvector/pgvector:0.8.6-pg16`
  so iterative-scan-era pgvector is the harness default). No `:latest`.
- Startup is health-gated via testcontainers wait strategies (`HttpWaitStrategy`
  on Qdrant `/readyz`, `ExecWaitStrategy` `pg_isready` for Postgres). Host ports
  are ephemeral (`with_exposed_ports`), not fixed binds.
- Hosted `ci.yml` is live on the public repo (Linux × 3.11/3.12/3.13). The commented
  `integration:` recipe in `.github/workflows/ci.yml` remains copy-paste: pull the
  pinned images, cache by hash of `containers.py`,
  `uv sync --group dev --extra qdrant --extra postgres`. P9-10 (local Docker
  `make verify`) is `cancelled` and is not this recipe.

## Consequences

**Buys:** contributors and a future Linux runner can exercise real engines
without a standing server. The package tree stays write-free (ADR-0001):
seeding lives in `tests/integration/seeding.py`.

**Costs:**
- Docker is a contributor prerequisite for the on-demand suite
  (`uv run pytest tests/integration -q --no-cov`). Local skips are loud;
  `CI=true` / `GITHUB_ACTIONS=true` turns a skip into a failure.
- `testcontainers` pulls `docker` / `requests`. That weight stays on the
  dev group, not on `uvx vhecfsck demo`.
- First image pull dominates wall time; subsequent runs reuse the local
  layer cache. Do not record a duration here until someone measures it.

## Alternatives considered

- **Product extra `[testcontainers]` / `uv sync --all-extras`.** Rejected:
  this is not an audit dependency (ADR-0002, lesson 5, ADR-0016).
- **`testcontainers[postgres]` / `[qdrant]` extras.** Rejected: those extras
  pull SQLAlchemy or a second `qdrant-client` path. Core `DockerContainer`
  plus wait strategies is enough; engine SDKs stay the product extras.
- **Compose file + `time.sleep`.** Rejected: port collisions and slow starts
  become the caller's problem. Wait strategies poll readiness.
- **Keep `VHECFSCK_POSTGRES_DSN` / embedded Qdrant as the only path.**
  Rejected for P7-03/P7-05/P7-07: reproductions need a real server and
  comparable seeding across engines.

## Revisit if

- `testcontainers` 5.x changes wait-strategy or port-mapping semantics.
- The pinned Qdrant / pgvector tags disappear, or `qdrant-client` 2.x forces
  a server bump.
- Hosted engine-integration job is enabled and the commented image-cache recipe
  needs a measured wall-time budget.
