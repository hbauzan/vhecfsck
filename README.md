# vhecfsck

Read-only, empirical, offline auditor for vector indexes. It answers one question
dashboards do not: *is this index still returning the right neighbours?*

<!-- TODO(P9-01): hero GIF — green dashboards beside collapsing recall -->

## Quickstart

Run the interactive CLI demonstration:

```bash
uvx vhecfsck demo
```

Or from a local checkout:

```bash
uv run vhecfsck demo
```

## What it is (and is not)

| Is | Is not |
| :--- | :--- |
| A CLI auditor you run against an index | A daemon, hosted SaaS, or dashboard replacement |
| Strictly read-only (no writes, no VACUUM, no reindex) | A repair / remediation tool |
| Empirical measurements against ground truth | A heuristic “health score” without evidence |

See [roadmap/00-vision-and-scope.md](roadmap/00-vision-and-scope.md) and
[ADR-0001](roadmap/adr/0001-read-only-by-default.md).

## Engine Adapters

- **LanceDB / Lance**: Read-only snapshot audits (`--dataset-version N`), exact deletion accounting, vector streaming, native k-NN search, and IVF partition introspection. See [LanceDB Guide](docs/engines/lancedb.md).
- **Qdrant**: Read-only HTTP/gRPC client. Point counts via collection info; deleted counts only when per-segment telemetry exists (otherwise DFI is `UNAVAILABLE`). Extra: `uv sync --extra qdrant`. See [Qdrant Guide](docs/engines/qdrant.md).
- **Postgres / pgvector**: Read-only session (`default_transaction_read_only=on`). Catalog introspection for HNSW/IVFFlat operator classes; DFI is a table-level proxy. Extra: `uv sync --extra postgres`. See [pgvector Guide](docs/engines/pgvector.md).

For a complete comparison of engine capabilities and metric exactness, see the [Consolidated Capability Matrix](docs/engines/capability-matrix.md).

## Status

Pre-alpha status: P0–P7 complete in `main` (including Qdrant, pgvector, and LanceDB adapters, container harness, graph stats evaluation, issue guards `qdrant#7147`, `pgvector#244`, and `lance#4164`, engine guides, and capability matrix). Hardening tickets P8-08, P8-09, and P8-11 are done. Next critical path is P8-01 calibration. Note: `docs/assets/vhecfsck-demo.gif` is a 320×180 deterministic NumPy raster stand-in; the launch hero GIF and full launch README land in [P9-01](roadmap/phases/phase-9-docs-release-and-launch.md). The `qdrant#7147` integration test serves as a regression guard (aggregate vs. grouped recall contrast is unit-tested in `test_canary_groups.py`; launch P9-04 relies on `pgvector#244` and `lance#4164`).

## Develop from a checkout

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.11. On macOS:

```bash
./setup.sh          # contributor panel: sync deps, run make verify when available
make verify         # single quality gate
make demo-gif       # regenerate docs/assets/vhecfsck-demo.gif
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Security

Read-only is an invariant. A hypothetical write path is a **security** issue, not a
bug — report it privately per [SECURITY.md](SECURITY.md).
