# vhecfsck — Vector Index Audit & Diagnostics

Read-only, empirical, offline auditor for vector indexes that detects silent recall decay and index pathologies before they reach production.

The name is a personalized play on Unix `fsck`: a vector-index checker, with an **H** from the author's name, Hector. Identifiers stay lowercase `vhecfsck`.

![vhecfsck demo](https://raw.githubusercontent.com/hbauzan/vhecfsck/main/docs/assets/vhecfsck-demo.gif)

## Quickstart

Run the interactive CLI demonstration from any machine with Python ≥ 3.11:

```bash
uvx vhecfsck demo
```

Or install via `pip`:

```bash
pip install vhecfsck
```

<!-- version:begin -->
Current release: [0.1.3](changelog.md) · [PyPI](https://pypi.org/project/vhecfsck/0.1.3/).
On GitHub Pages the changelog is `/changelog` (no trailing slash). `/changelog/` 404s, same as `/releasing/` versus `/releasing`.
<!-- version:end -->

---

## Core Principles

1. **Strictly Read-Only**: `vhecfsck` never executes writes, `VACUUM`, `REINDEX`, or state mutations.
2. **Empirical Measurements**: All diagnostic scores derive from exact k-NN ground truth computations.
3. **Zero Network Egress**: Air-gapped, zero telemetry, zero analytics, zero external script requests.
4. **Honest Capabilities**: Unsupported engine features report `UNAVAILABLE` (exit code `3`) rather than fake healthy scores.

---

## Documentation Overview

* [Concepts & Pathologies](concepts.md): Deep dive into silent recall decay, hubness, tombstone accumulation, and centroid drift.
* [Metrics Reference](metrics.md): Normative specifications and formulas derived from `02-metrics-spec.md`.
* [Engine Guides](engines/capability-matrix.md): Setup and introspection guides for LanceDB, Qdrant, and pgvector.
* [CI Integration](ci-integration.md): Copy-pasteable recipes for GitHub Actions, GitLab CI, Kubernetes, and Prometheus.
* [Read-Only Guarantee](read-only.md): Technical verification details and security invariants.
* [Calibration & Thresholds](calibration/README.md): Empirical threshold calibration across dimensions $d \in [64, 1536]$.
* [Performance Budgets](performance.md): Hardware guidance and scaling benchmarks up to 1,000,000 vectors.
* [CLI Reference](cli-reference.md): Programmatically generated Typer CLI reference.
* [Report Schema Reference](schema-reference.md): Programmatically generated Pydantic v1.1 JSON schema reference.
