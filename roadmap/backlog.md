# Backlog Tracker

A flat index of every ticket. **Full detail lives in the phase files** — this document exists to
answer "what is next?" and "what is blocked?" without opening ten files. It deliberately does not
duplicate ticket contracts; duplicated specifications drift, and then nobody knows which copy is
authoritative.

**Sizes:** `S` one file, one concept, under ~150 lines including tests · `M` two or three files,
one coherent feature · `L` should have been split; allowed only where a contract must land
atomically.

**Status values:** `todo` · `in-progress` · `blocked` · `done` · `cancelled`.

**Start here:** `P0-01`. It has no dependencies and creates the first line of production code.

---

## P0 — Foundation and guardrails · [phase file](phases/phase-0-foundation.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P0-01 | Bootstrap package and packaging | M | — | done |
| P0-02 | Lint, format and strict typing configuration | S | P0-01 | done |
| P0-03 | Test harness and coverage gates | S | P0-01 | done |
| P0-04 | `make verify` as the single quality gate | S | P0-02, P0-03 | done |
| P0-05 | Error taxonomy and exit-code contract | M | P0-01 | done |
| P0-06 | Structured logging with credential redaction | M | P0-05 | done |
| P0-07 | Configuration and default threshold profile | M | P0-01 | done |
| P0-08 | Import-layering enforcement | S | P0-04 | todo |
| P0-09 | Read-only static guard | M | P0-04 | todo |
| P0-10 | Continuous integration | M | P0-04 | todo |
| P0-11 | Community, security and licence files | S | P0-01 | todo |
| P0-12 | Agent operating rules at the repository root | S | P0-11 | todo |
| P0-13 | Reserve the project namespace | S | P0-01 | todo |
| P0-14 | Pre-commit hooks | S | P0-04, P0-09 | todo |
| P0-15 | Contributor console (`setup.sh`) | M | P0-01 | done |

## P1 — Synthetic corpus and adapter protocol · [phase file](phases/phase-1-synthetic-and-adapter-protocol.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P1-01 | Shared domain types | M | P0-07 | todo |
| P1-02 | `IndexAdapter` protocol | L | P1-01 | todo |
| P1-03 | Synthetic corpus generator | M | P1-01 | todo |
| P1-04 | Injectable pathologies | M | P1-03 | todo |
| P1-05 | `SyntheticAdapter` with a real approximate-search model | L | P1-02, P1-04 | todo |
| P1-06 | Adapter registry and target URI resolution | S | P1-05 | todo |
| P1-07 | Shared adapter contract suite | L | P1-02, P1-05 | todo |
| P1-08 | Named scenarios | M | P1-04, P1-05 | todo |

## P2 — Metrics engine · [phase file](phases/phase-2-metrics-engine.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P2-01 | Metric result types and verdict model | M | P1-01 | todo |
| P2-02 | Deterministic sampling | S | P0-07 | todo |
| P2-03 | Naive reference implementations (oracle) | M | P1-01 | todo |
| P2-04 | Blocked BLAS ground truth | L | P2-03 | todo |
| P2-05 | Canary recall | M | P2-04 | todo |
| P2-06 | Hubness | L | P2-04 | todo |
| P2-07 | Deletion fragmentation index | S | P2-01 | todo |
| P2-08 | Partition size CV | S | P2-01 | todo |
| P2-09 | Verdict engine | S | P2-01, P0-07 | todo |
| P2-10 | Audit pipeline orchestration | M | P2-05 … P2-09 | todo |
| P2-11 | Determinism harness | S | P2-10 | todo |

## P3 — Report and CLI · [phase file](phases/phase-3-report-and-cli.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P3-01 | Report schema | M | P2-01 | todo |
| P3-02 | JSON renderer and published schema | M | P3-01 | todo |
| P3-03 | Terminal renderer | M | P3-01 | todo |
| P3-04 | `vhecfsck audit` | M | P3-02, P3-03, P2-10 | todo |
| P3-05 | `vhecfsck demo` | S | P3-04, P1-08 | todo |
| P3-06 | Prometheus exporter | M | P3-01 | todo |
| P3-07 | `vhecfsck export` | S | P3-02 | todo |
| P3-08 | Exit-code contract test suite | S | P3-04, P3-05 | todo |

## P4 — Projection and 3D slice · [phase file](phases/phase-4-projection-and-3d-slice.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P4-01 | Deterministic 3D projection | M | P2-04 | todo |
| P4-02 | Scene payload model | M | P3-01, P4-01 | todo |
| P4-03 | Level-of-detail decimation | M | P4-02 | todo |
| P4-04 | Binary scene transport | M | P4-02 | todo |
| P4-05 | FastAPI server | M | P4-04, P2-10 | todo |
| P4-06 | `vhecfsck serve` | S | P4-05 | todo |
| P4-07 | Front-end scaffold | M | P0-10 | todo |
| P4-08 | Point-cloud renderer | L | P4-07, P4-04 | todo |
| P4-09 | Report HUD | M | P4-08 | todo |
| P4-10 | Visual regression baseline | M | P4-09 | todo |
| P4-11 | Bundle the front end into the wheel | M | P4-07, P0-01 | todo |

> **MVP gate** after P4. Run the checklist in [`03-phases-overview.md §4`](03-phases-overview.md)
> before starting anything below this line.

## P5 — LanceDB adapter · [phase file](phases/phase-5-lancedb-adapter.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P5-01 | Dataset discovery and descriptor | M | P1-02 | todo |
| P5-02 | Version pinning for a consistent snapshot | S | P5-01 | todo |
| P5-03 | Exact deletion accounting | M | P5-01 | todo |
| P5-04 | Vector enumeration and random access | M | P5-01 | todo |
| P5-05 | Engine search | M | P5-01 | todo |
| P5-06 | IVF partition introspection | M | P5-01 | todo |
| P5-07 | Read-only verification harness | M | P5-04, P5-05 | todo |
| P5-08 | Version compatibility matrix | S | P5-01 | todo |
| P5-09 | Reproduce `lance#4164` | M | P5-05, P5-06 | todo |
| P5-10 | LanceDB user guide | S | P5-09 | todo |

## P6 — Visualizer depth · [phase file](phases/phase-6-visualizer-depth.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P6-01 | Scale to a 1M-point corpus | L | P4-03, P4-08 | todo |
| P6-02 | Live audit progress | M | P4-05 | todo |
| P6-03 | Interactive query probe | L | P6-01 | todo |
| P6-04 | Partition and distribution views | M | P6-01 | todo |
| P6-05 | Tombstone layer | M | P6-01 | todo |
| P6-06 | Camera presets and guided tour | M | P6-04, P6-05 | todo |
| P6-07 | Deterministic capture for the README asset | M | P6-06 | todo |
| P6-08 | Accessibility and palette review | S | P6-04 | todo |
| P6-09 | Expanded visual regression coverage | M | P6-04, P6-05, P6-08 | todo |

## P7 — Qdrant and pgvector adapters · [phase file](phases/phase-7-qdrant-and-pgvector-adapters.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P7-01 | Container-based integration harness | M | P0-10 | todo |
| P7-02 | Qdrant adapter: descriptor, counts, telemetry trap | L | P1-02, P7-01 | todo |
| P7-03 | Reproduce `qdrant#7147` (multitenant subgraph corruption) | L | P7-02 | todo |
| P7-04 | pgvector adapter: read-only session and catalog introspection | L | P1-02, P7-01 | todo |
| P7-05 | Reproduce `pgvector#244` (dead tuples collapse recall) | M | P7-04 | todo |
| P7-06 | HNSW graph statistics (best effort) | M | P7-02, P7-04 | todo |
| P7-07 | Cross-engine consistency suite | M | P5, P7-02, P7-04 | todo |
| P7-08 | Engine guides and capability matrix | M | P7-02, P7-04, P7-06 | todo |

## P8 — Calibration and hardening · [phase file](phases/phase-8-calibration-and-hardening.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P8-01 | Reference dataset calibration harness | L | P7 | todo |
| P8-02 | Calibrate and justify the default thresholds | M | P8-01 | todo |
| P8-03 | Baseline and delta mode | L | P3-01, P8-02 | todo |
| P8-04 | Performance budgets | M | P2-04, P5 | todo |
| P8-05 | Resource ceilings and graceful degradation | M | P2-10 | todo |
| P8-06 | Concurrency and chaos | M | P5, P7 | todo |
| P8-07 | Mutation testing on the numeric core | M | P2 | todo |
| P8-08 | Fuzzing and adversarial inputs | M | P2, P3 | todo |
| P8-09 | Error message audit | S | P0-05 | todo |
| P8-10 | Read-only assurance across all engines | M | P5-07, P7 | todo |
| P8-11 | Supply chain and dependency review | S | P0-10 | todo |

## P9 — Documentation, release and launch · [phase file](phases/phase-9-docs-release-and-launch.md)

| ID | Title | Size | Depends on | Status |
| :--- | :--- | :--- | :--- | :--- |
| P9-01 | README | M | P6-07, P8-04 | todo |
| P9-02 | Documentation site | M | P9-01 | todo |
| P9-03 | CI integration recipes | M | P3-08 | todo |
| P9-04 | Verify the anchor issues and write the launch post | M | P5-09, P7-03, P7-05 | todo |
| P9-05 | Release engineering | M | P4-11, P8-11 | todo |
| P9-06 | Pre-launch review pass | M | P9-01, P9-02, P9-03 | todo |
| P9-07 | Launch | M | P9-04, P9-05, P9-06 | todo |
| P9-08 | Post-launch triage window | M | P9-07 | todo |
| P9-09 | Linux port of `setup.sh` | S | P0-15, owner publish go-ahead | todo |

---

## Critical path to the MVP

The shortest dependency chain from an empty repository to a working audit. Everything else can
proceed in parallel around it, so if throughput is limited, protect this chain first.

```text
P0-01 → P0-02/03 → P0-04 → P0-07 → P1-01 → P1-02 → P1-05 → P2-03 → P2-04
      → P2-05 → P2-10 → P3-01 → P3-04 → P3-05 → P4-01 → P4-02 → P4-04
      → P4-05 → P4-08 → MVP gate
```

Two things on this chain deserve extra care because everything downstream depends on their
correctness rather than merely on their existence:

- **`P2-04` (blocked BLAS ground truth)** is the oracle for every metric. A bug here is invisible
  to every other test, because everything else is measured against it. Its block-size-invariance
  test is the most valuable single test in the project.
- **`P1-02` (adapter protocol)** is the contract three engines will have to satisfy. It is designed
  before any real engine exists, and `P5`'s explicit success criterion is that it needed no
  breaking change.

## Parallelisable work

Independent of the critical path once their dependencies are met, and useful for filling capacity:

- `P0-05`, `P0-06`, `P0-09`, `P0-11`, `P0-12`, `P0-13`, `P0-14`, `P0-15`
- `P1-03`, `P1-04`, `P1-06`, `P1-08`
- `P2-02`, `P2-07`, `P2-08`, `P2-09`, `P2-11`
- `P3-02`, `P3-03`, `P3-06`, `P3-07`, `P3-08`
- `P4-03`, `P4-06`, `P4-07`, `P4-09`, `P4-10`, `P4-11`
- Post-MVP: all of `P5`, `P6` and `P7` are mutually independent.

## Totals

| Phase | Tickets | S | M | L |
| :--- | ---: | ---: | ---: | ---: |
| P0 | 15 | 8 | 7 | 0 |
| P1 | 8 | 1 | 4 | 3 |
| P2 | 11 | 5 | 4 | 2 |
| P3 | 8 | 3 | 5 | 0 |
| P4 | 11 | 2 | 8 | 1 |
| P5 | 10 | 3 | 7 | 0 |
| P6 | 9 | 1 | 6 | 2 |
| P7 | 8 | 0 | 4 | 4 |
| P8 | 11 | 2 | 7 | 2 |
| P9 | 9 | 1 | 8 | 0 |
| **Total** | **100** | **26** | **60** | **14** |

The fourteen `L` tickets are the ones to watch. Each should be re-examined before starting: if it
can be split into independently verifiable pieces, split it. The only legitimate reason for an `L`
is a contract that must land atomically — a protocol definition, a schema, a codec with two sides.
