# vhecfsck — Roadmap

> Topological audit and health diagnostics for vector indexes.
> `fsck` and `smartctl`, but for HNSW graphs and IVF partitions.

This directory is the **normative planning source** for `vhecfsck`. It is written to be
executed by AI coding agents working one ticket at a time, with a green test suite after
every ticket. There are no calendar dates: progress is gated by verifiable acceptance
criteria, not by elapsed time.

## How to use this roadmap

1. Read [`next-ticket.md`](next-ticket.md). One agent, one ticket, in that order.
   Do not start at `P0-01`.
2. Read [`lessons-learned.md`](lessons-learned.md) §0 (cold start) and
   [`agent-playbook.md`](agent-playbook.md) for the workflow that applies to every ticket.
3. Open the ticket contract named by `next-ticket.md` — remaining work lives in
   [`archive/plans/`](archive/plans/) and [`archive/phases/`](archive/phases/).
   [`phases/`](phases/) only still holds P10.
4. Before implementing any metric, read the relevant section of
   [`02-metrics-spec.md`](02-metrics-spec.md). It is normative and overrides prose
   elsewhere.
5. Do not re-litigate settled decisions. Check [`adr/`](adr/) first; if you must deviate,
   write a new ADR that supersedes the old one.

## Document map

| Document | Purpose | Normative? |
| :--- | :--- | :--- |
| [`00-vision-and-scope.md`](00-vision-and-scope.md) | Problem, thesis, personas, in-scope / out-of-scope, success criteria | Yes (scope) |
| [`01-architecture.md`](01-architecture.md) | Module layout, contracts, data flow, dependency rules | Yes (structure) |
| [`02-metrics-spec.md`](02-metrics-spec.md) | Exact definition of every metric, thresholds, edge cases, oracles | Yes (behaviour) |
| [`03-phases-overview.md`](03-phases-overview.md) | Phase map, dependency DAG, phase exit gates | Yes (sequencing) |
| [`next-ticket.md`](next-ticket.md) | Dispatcher: next `todo` ticket, in order | Yes (queue) |
| [`phases/`](phases/) | Open horizon only (P10). P0–P9 contracts are in [`archive/phases/`](archive/phases/) | Yes (work items) |
| [`archive/`](archive/) | Completed phases, sub-plans, historical lessons, handoffs | Historical |
| [`adr/`](adr/) | Architecture Decision Records — the "why", and what not to revisit | Yes (decisions) |
| [`backlog.md`](backlog.md) | Flat ticket tracker: ID, phase, deps, size, status | Tracking only |
| [`testing-strategy.md`](testing-strategy.md) | Test layers, oracles, determinism, coverage and CI gates | Yes (quality bar) |
| [`risk-register.md`](risk-register.md) | Risks, triggers, mitigations, owning tickets | Advisory |
| [`release-plan.md`](release-plan.md) | Versioning, packaging, CI/CD, PyPI, launch | Yes (release) |
| [`agent-playbook.md`](agent-playbook.md) | Execution protocol and guardrails for AI agents | Yes (process) |
| [`lessons-learned.md`](lessons-learned.md) | Active handoff memory (invariants). P0–P7 write-ups: [`archive/lessons-learned-historical.md`](archive/lessons-learned-historical.md) | Process |
| [`archive/plans/plan_optimizacion_test_harness.md`](archive/plans/plan_optimizacion_test_harness.md) | Test harness empirical benchmarks (TH remaining via `next-ticket.md`) | Tracking only |
| [`archive/plans/plan_integridad_matematica.md`](archive/plans/plan_integridad_matematica.md) | Metric-integrity findings (MI remaining via `next-ticket.md`) | Tracking only |
| [`archive/handoffs/dev-protocol-followups.md`](archive/handoffs/dev-protocol-followups.md) | Queued work on the dev-protocol pack itself | Tracking only |
| [`glossary.md`](glossary.md) | HNSW, IVF, tombstone, hubness, DFI, and friends | Reference |

## Project parameters fixed by the owner

These are settled inputs, not open questions. They constrain every phase.

| Parameter | Decision |
| :--- | :--- |
| Canonical name | `vhecfsck` (lowercase) — package, CLI binary, repo, PyPI project |
| First adapter | Synthetic in-memory NumPy adapter, **before** any real engine |
| Build order | Thin end-to-end vertical slice (audit → JSON report → 3D scene) first, then depth on each branch |
| Scale target | Up to ~1M vectors × 768D on a single node, blocked BLAS in RAM |
| Work sizing | Modular agent-sized tickets, tests always, no time estimates |
| Documentation language | English (all artifacts, code, docs, commits) |
| Distribution | Public open source on GitHub + published to PyPI |
| Invasiveness | Strictly read-only against every target, no exceptions |

## Phase map at a glance

```text
P0  Foundation & guardrails ....... repo, tooling, CI, verify gate, name reservation
P1  Synthetic corpus & adapter ⟶ .. IndexAdapter protocol, pathology generator, contract suite
P2  Metrics engine ................ canary, hubness, fragmentation, partitions, verdicts
P3  Report + CLI (retention) ...... schemas, Typer CLI, exit codes, Prometheus       ┐ vertical
P4  Projection + 3D (showcase) .... PCA, scene payload, FastAPI serve, Three.js SPA  ┘ slice
────────────────────────── MVP / v0.1.0-rc gate ──────────────────────────
P5  LanceDB adapter ............... first real engine, IVF introspection, lance#4164 repro
P6  Visualizer depth .............. LOD to 1M pts, live streaming, query probe
P7  Qdrant + pgvector adapters .... qdrant#7147 and pgvector#244 repros, CI matrix
P8  Calibration & hardening ....... threshold calibration, perf budgets, read-only audit
P9  Docs, release & launch ........ README GIF, PyPI trusted publishing, v0.1.0
P10 Post-1.0 horizon (not planned in detail)
```

See [`03-phases-overview.md`](03-phases-overview.md) for the dependency DAG and exit gates.

## Known corrections applied to the source specification

The upstream architecture blueprint (v1.0.0-PROD, authored as `VECFSCK`) was reviewed
before this roadmap was written. The following defects were found and are corrected here.
Each correction has an owning ADR so the reasoning survives.

| # | Defect in source spec | Correction | Where |
| :--- | :--- | :--- | :--- |
| 1 | Anti-Hub Fraction and Hub Share are defined over `Q=200` queries. With `K=10` at most 2,000 vectors can ever be hit, so on a 1M corpus anti-hub fraction is ≥0.998 and the check fails unconditionally. The published thresholds (warn 0.25 / fail 0.40) come from the classical hubness regime where every point is a query. | Hubness metrics run on their **own** self-queried subsample (`S` points, all used as queries against the subsample, self excluded). Sampling is decoupled from canary recall. | [ADR-0006](adr/0006-hubness-sampling-regime.md), [metrics §3](02-metrics-spec.md) |
| 2 | Ground truth is described as `float32`/`float16` BLAS. `float16` accumulation over 768 dimensions loses enough precision to reorder near-ties, corrupting the very oracle everything is measured against. | Storage may be `float16`; accumulation is **always** `float32` minimum, with a `float64` cross-check on a small slice. | [ADR-0005](adr/0005-ground-truth-precision-and-blocking.md), [metrics §2](02-metrics-spec.md) |
| 3 | Recall is defined as a set intersection of IDs. Equidistant neighbours at the `K` boundary make an engine look wrong when it is right. | Report both `recall_id` (strict) and `recall_dist` (tie-tolerant, distance-thresholded). `recall_dist` is the gated canary value. | [ADR-0007](adr/0007-tie-tolerant-recall.md), [metrics §2](02-metrics-spec.md) |
| 4 | Queries "from the log or the corpus" are treated as equivalent. Corpus-drawn queries are their own nearest neighbour at distance 0, inflating recall by roughly `1/K`. | Self-matches are excluded by default; corpus-drawn queries are labelled a weaker evidence class in the report. | [metrics §2](02-metrics-spec.md) |
| 5 | Unavailable metrics have no representation, so an engine that cannot report dead-tuple counts would silently score a perfect DFI of 0. | Every metric is tri-state plus `UNAVAILABLE`, which never counts as a pass. Dedicated exit code, promotable to failure with `--strict-unavailable`. | [ADR-0004](adr/0004-metric-result-states-and-exit-codes.md) |
| 6 | Exit codes cover only `0/1/2`, leaving tool crashes and misconfiguration indistinguishable from a genuine `FAIL` verdict — the worst possible outcome for a CI gate. | Reserved codes for inconclusive, usage error and internal error. | [ADR-0004](adr/0004-metric-result-states-and-exit-codes.md) |
| 7 | Absolute thresholds are presented as universal, but healthy values are dataset- and metric-space-dependent. Uncalibrated thresholds produce false alarms, and a noisy checker gets disabled. | Thresholds are configurable, ship calibrated defaults, and are complemented by a baseline/delta mode. | [ADR-0011](adr/0011-thresholds-and-baseline-mode.md), [P8](archive/phases/phase-8-calibration-and-hardening.md) |
| 8 | A 1M-point scene sent as JSON is hundreds of megabytes and will not render. | Scene payloads use a binary transport with server-side level-of-detail decimation. | [ADR-0009](adr/0009-scene-transport-and-lod.md) |

## Status

P0–P9 execution is complete except the residual queue in
[`next-ticket.md`](next-ticket.md) (MI-05, TH-06…TH-08, P9-12). Product on
`main` is the read-only CLI auditor; hero command `uvx vhecfsck demo`. P10 stays
unplanned in [`phases/phase-10-post-1.0-horizon.md`](phases/phase-10-post-1.0-horizon.md).
