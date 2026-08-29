# 03 — Phases Overview

## 1. Sequencing principles

There are no dates in this roadmap. Progress is measured by verifiable gates, because the
work is executed by AI agents whose throughput is unpredictable but whose output can be
checked exactly.

Five principles shaped the ordering:

1. **Synthetic before real.** The first adapter is an in-memory NumPy corpus with no
   external dependency. Every metric is validated against data whose true value is known by
   construction, before any engine SDK, network call, or Docker container enters the
   picture. When a metric later disagrees with LanceDB, we already know the metric is right,
   so the bug is in the adapter. Without this, every failure has two suspects.
2. **Thin vertical slice before depth.** Phases 0–4 produce a complete, unimpressive but
   working path: audit a synthetic corpus, gate on real metrics, emit a JSON report, render
   it in 3D. Both front ends exist early, badly, and are then deepened — rather than one
   being designed against an imagined report schema that turns out to be wrong.
3. **Oracle before optimisation.** Every fast path is written after the naive path it will
   be differentially tested against. `O(N²)` reference implementations are permanent test
   assets, not scaffolding to be deleted.
4. **Gates are executable.** A phase is complete when a named command exits zero, not when
   it feels finished. Every gate below is a command someone can run.
5. **One ticket, one agent session, one commit.** Each ticket ends with `make verify` green
   and a single conventional commit. A ticket that cannot be finished and verified in one
   session is too big and must be split before starting.

## 2. Dependency graph

```text
                         ┌──────────────────────────────┐
                         │ P0  Foundation & guardrails  │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │ P1  Synthetic corpus +       │
                         │     IndexAdapter protocol    │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │ P2  Metrics engine (core/)   │
                         └───────┬──────────────┬───────┘
                                 │              │
              ┌──────────────────▼──┐        ┌──▼───────────────────┐
              │ P3  Report + CLI    │        │ P4  Projection + 3D  │
              │     (retention)     │        │     (showcase)       │
              └──────────┬──────────┘        └──────────┬───────────┘
                         └────────────┬─────────────────┘
                                      │
                      ══════ MVP / v0.1.0-rc gate ══════
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
┌─────────▼─────────┐   ┌─────────────▼────────┐   ┌──────────────▼───────┐
│ P5  LanceDB       │   │ P6  Visualizer depth │   │ P7  Qdrant +         │
│     adapter       │   │     (needs P4)       │   │     pgvector         │
└─────────┬─────────┘   └─────────────┬────────┘   └──────────────┬───────┘
          └───────────────────────────┼───────────────────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │ P8  Calibration & hardening  │
                       └──────────────┬───────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │ P9  Docs, release & launch   │
                       └──────────────────────────────┘
```

`P5`, `P6` and `P7` are mutually independent once the MVP gate is passed and may proceed in
any order or in parallel. `P7` depends on `P5` only for the lessons the first real adapter
teaches — if the adapter contract survives LanceDB unchanged, it will survive Qdrant.

## 3. Phases

| Phase | Name | Delivers | Exit gate command |
| :--- | :--- | :--- | :--- |
| [P0](phases/phase-0-foundation.md) | Foundation & guardrails | Repo, packaging, lint/type/test tooling, CI, `make verify`, layering enforcement, reserved names | `make verify && vhecfsck --version` |
| [P1](phases/phase-1-synthetic-and-adapter-protocol.md) | Synthetic corpus & adapter protocol | `IndexAdapter` protocol, synthetic adapter, pathology generator, shared contract suite | `pytest tests/contract tests/unit -q` |
| [P2](phases/phase-2-metrics-engine.md) | Metrics engine | Ground truth, all five metrics, verdict engine, oracles, property tests | `pytest tests/oracle tests/property -q` |
| [P3](phases/phase-3-report-and-cli.md) | Report & CLI (retention) | Report schema, renderers, Typer CLI, exit-code contract, Prometheus | `vhecfsck demo --scenario healthy; echo $?` → `0` |
| [P4](phases/phase-4-projection-and-3d-slice.md) | Projection & 3D slice (showcase) | Deterministic PCA, scene payload, FastAPI serve, minimal Three.js SPA | `pytest tests/e2e -q && npm --prefix vhecfsck/web test` |
| [P5](phases/phase-5-lancedb-adapter.md) | LanceDB adapter | Real engine, IVF introspection, deletion accounting, `lance#4164` reproduction | `pytest tests/integration -k lancedb -q` |
| [P6](phases/phase-6-visualizer-depth.md) | Visualizer depth | LOD to 1M points, live progress streaming, interactive query probe | `npm --prefix vhecfsck/web run test:visual` |
| [P7](phases/phase-7-qdrant-and-pgvector-adapters.md) | Qdrant & pgvector adapters | Two more engines, `qdrant#7147` and `pgvector#244` reproductions | `pytest tests/integration -q` (full matrix) |
| [P8](phases/phase-8-calibration-and-hardening.md) | Calibration & hardening | Calibrated thresholds, baseline mode, perf budgets, read-only audit, mutation testing | `make verify-full` |
| [P9](phases/phase-9-docs-release-and-launch.md) | Docs, release & launch | README GIF, docs, trusted publishing, `v0.1.0`, launch content | `uvx vhecfsck@0.1.0 demo` from a clean machine |
| [P10](phases/phase-10-post-1.0-horizon.md) | Post-1.0 horizon | Deliberately unplanned: candidate directions only | — |

## 4. The MVP gate

Passing `P4` means the following is simultaneously true. This is the checklist to run before
declaring the MVP done — not a summary, an actual gate.

- [ ] `uvx vhecfsck demo` works on a machine with no database, no dataset, and no Node
      toolchain, and visibly reproduces a recall collapse.
- [ ] All five metrics compute against the synthetic adapter and each is validated both
      against a naive oracle and against a synthetic dataset with a known true value.
- [ ] Exit codes are correct for every scenario: healthy → `0`, degraded → `1`, broken →
      `2`, capability-limited → `3`, bad flags → `4`.
- [ ] Two runs at the same seed produce byte-identical JSON reports.
- [ ] `make verify` is green: ruff, ruff format, `mypy --strict` on `core`/`models`/
      `adapters`, pytest, coverage ≥90% on `core/` and ≥80% overall, import-layering
      contracts satisfied.
- [ ] The 3D view renders the synthetic corpus with hubs red, anti-hubs blue and tombstones
      translucent grey, driven entirely by report data with zero metric logic in the front
      end.
- [ ] Prometheus textfile output is valid and scrapes cleanly with `promtool check metrics`.
- [ ] No adapter contains a write API call, verified by the CI grep check.

## 5. Ticket sizing

| Size | Meaning |
| :--- | :--- |
| **S** | One file, one concept, roughly under 150 lines including tests. |
| **M** | Two or three files, one coherent feature, tests in two layers. |
| **L** | Should have been split. Allowed only where a contract must land atomically (a protocol definition, a schema). If a ticket labelled **L** can be split, split it first. |

Every ticket, regardless of size, must satisfy the definition of done in
[`agent-playbook.md`](agent-playbook.md). There are no exceptions for "small" tickets — a
one-line change with no test is not a smaller version of the work, it is a different and
worse kind of work.
