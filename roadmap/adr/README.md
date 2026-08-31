# Architecture Decision Records

Each ADR records one decision, why it was made, and what it costs. The point is not
documentation for its own sake — it is to stop a future contributor (human or agent) from
re-opening a settled question, and to make it obvious when a decision genuinely should be
revisited because its stated conditions changed.

## Rules

1. **Read before deviating.** If an implementation ticket seems to require contradicting an
   ADR, stop. Either the ticket is wrong or the ADR needs superseding. Both are decisions, not
   improvisations.
2. **Never edit a decision retroactively.** Write a new ADR with status `Accepted` that
   supersedes the old one, and mark the old one `Superseded by ADR-NNNN`. The record of what we
   used to believe, and why we changed, is the valuable part.
3. **Every ADR has a "Revisit if" section.** A decision with no stated conditions for
   reconsideration is dogma. Stating the trigger is what makes the decision falsifiable.
4. **Adding a dependency requires an ADR.** No exceptions. Dependency footprint is a feature
   of an infrastructure tool that people install next to their production database.

## Index

| ID | Title | Status | Affects |
| :--- | :--- | :--- | :--- |
| [0001](0001-read-only-by-default.md) | Strictly read-only, enforced structurally | Accepted | Everything |
| [0002](0002-packaging-and-toolchain.md) | Python floor, uv + hatchling, lean base install | Accepted | P0 |
| [0003](0003-empirical-metrics-only.md) | Empirical metrics only; no abstract estimators | Accepted | P2 |
| [0004](0004-metric-result-states-and-exit-codes.md) | Tri-state plus UNAVAILABLE; six exit codes | Accepted | P0, P2, P3 |
| [0005](0005-ground-truth-precision-and-blocking.md) | float32 accumulation, blocked BLAS, 1M ceiling | Accepted | P2 |
| [0006](0006-hubness-sampling-regime.md) | Hubness uses a self-queried subsample | Accepted | P2 |
| [0007](0007-tie-tolerant-recall.md) | Gate on distance-thresholded recall | Accepted | P2 |
| [0008](0008-report-schema-versioning.md) | Report is a versioned public contract | Accepted | P3 |
| [0009](0009-scene-transport-and-lod.md) | Binary scene transport, class-stratified LOD | Accepted | P4 |
| [0010](0010-frontend-build-and-bundling.md) | Vite + TypeScript, built in CI, bundled in the wheel | Accepted | P4 |
| [0011](0011-thresholds-and-baseline-mode.md) | Configurable thresholds plus baseline/delta gating | Accepted | P0, P8 |
| [0012](0012-naming.md) | Canonical name `vhecfsck` | Accepted (one open question) | All |
| [0013](0013-adapter-protocol.md) | Structural Protocol with honest capabilities | Accepted | P1, P5, P7 |
| [0014](0014-synthetic-adapter-first.md) | Synthetic adapter before any real engine | Accepted | P1 |
| [0015](0015-axe-core-playwright.md) | @axe-core/playwright for Visualizer Accessibility E2E Testing | Accepted | P4, P6, P9 |
| [0016](0016-qdrant-postgres-extras.md) | Optional extras for Qdrant and Postgres / pgvector | Accepted | P7 |
| [0017](0017-hypothesis-fuzzing-dev-dependency.md) | Hypothesis as a dev dependency for core fuzzing | Accepted | P8 |
| [0018](0018-testcontainers-dev-dependency.md) | testcontainers as a harness-only dev dependency | Accepted | P7 |

## Template

```markdown
# ADR-NNNN — Title

**Status:** Proposed | Accepted | Superseded by ADR-NNNN
**Affects:** phases / modules

## Context
What forced a decision. Include the constraint that makes the obvious answer wrong.

## Decision
What we do, stated so an implementer cannot misread it.

## Consequences
What this buys, and what it costs. The cost section is mandatory and must be honest.

## Alternatives considered
What was rejected and why. Enough detail that nobody has to rediscover it.

## Revisit if
The specific conditions under which this should be reconsidered.
```
