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

## Status

Pre-alpha. Capabilities ship ticket-by-ticket; this README will not claim a
benchmark, engine support matrix, or exit-code behaviour until those are measured
and implemented. The full launch README is [P9-01](roadmap/phases/phase-9-docs-release-and-launch.md).

## Develop from a checkout

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.11. On macOS:

```bash
./setup.sh          # contributor panel: sync deps, run make verify when available
make verify         # single quality gate
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Security

Read-only is an invariant. A hypothetical write path is a **security** issue, not a
bug — report it privately per [SECURITY.md](SECURITY.md).
