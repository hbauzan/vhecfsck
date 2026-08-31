# vhecfsck

Read-only, empirical, offline auditor for vector indexes. It answers one question
dashboards do not: *is this index still returning the right neighbours?*

<!-- TODO(P9-01): hero GIF — green dashboards beside collapsing recall -->

## Quickstart

The intended first-run path (hero command):

```bash
uvx vhecfsck demo
```

`demo` lands in a later ticket (P3-05). Until then the package is installable as a
pre-alpha CLI stub; contributor workflows use a git checkout (see below).

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
- **Qdrant**: Read-only HTTP/gRPC or local/embedded client. Point counts via the count API; deleted counts only when per-segment telemetry exists (otherwise DFI is `UNAVAILABLE`). Extra: `pip install "vhecfsck[qdrant]"`.
- **Postgres / pgvector**: Read-only session (`default_transaction_read_only=on`). Catalog introspection for HNSW/IVFFlat operator classes; DFI is a table-level proxy. Extra: `pip install "vhecfsck[postgres]"`.

## Status

Phase 7 Qdrant / pgvector adapters landed (P7-02, P7-04). P8-08 hypothesis
fuzzing is in. Container harness and issue reproductions (`qdrant#7147`,
`pgvector#244`) remain. Pre-alpha capabilities ship ticket-by-ticket; this
README will not claim a benchmark or exit-code behaviour until measured and
implemented. The full launch README is
[P9-01](roadmap/phases/phase-9-docs-release-and-launch.md).

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
