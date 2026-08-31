# 01 — Architecture

## 1. Shape of the system

`vhecfsck` is a satellite tool: a single Python package that reads from a target index and
emits a report. It has no daemon, no database of its own, and no position in anyone's
request path.

```text
                          ┌──────────────────────────────┐
   read-only              │        Audit pipeline        │
   ┌──────────┐  batches  │                              │
   │  target  │──────────▶│  Adapter ──▶ CorpusView      │
   │  index   │◀─ search ─│                 │            │
   └──────────┘  queries  │                 ▼            │
    LanceDB /             │           core/ metrics      │
    Qdrant /              │       (ground truth, canary, │
    pgvector /            │        hubness, DFI, CV)     │
    synthetic             │                 │            │
                          │                 ▼            │
                          │      MetricResult[] ──▶ Report (versioned)
                          └──────────────────────────────┘
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 ▼                      ▼                      ▼
          text renderer          json / prometheus       ScenePayload
          (terminal)             (CI, dashboards)        (binary + LOD)
                 │                      │                      │
                 └──── exit code ───────┘                      ▼
                                                     FastAPI ──▶ Three.js SPA
```

Two rules make this diagram enforceable rather than decorative:

1. **Data flows left to right.** Metrics never call adapters directly for anything the
   pipeline did not hand them; renderers never compute anything.
2. **The `Report` is the only contract between the engine and the front ends.** If the 3D
   view needs a number, that number becomes part of the report schema. It does not become a
   second code path into `core/`.

## 2. Repository layout

```text
vhecfsck/
├── pyproject.toml               # uv + hatchling; single source of version truth
├── README.md                    # hero GIF + one-line quickstart
├── AGENTS.md                    # hand-written / opt-out distill of agent-playbook.md (lesson 16)
├── LICENSE                      # Apache-2.0
├── CHANGELOG.md                 # keep-a-changelog, release-automated
├── Makefile                     # `make verify` is the single quality gate
├── roadmap/                     # this directory — planning source of truth
├── vhecfsck/
│   ├── __init__.py              # __version__ only; no side effects, no heavy imports
│   ├── __main__.py              # `python -m vhecfsck`
│   ├── cli.py                   # Typer app: audit | demo | serve | export | version
│   ├── config.py                # AuditConfig, threshold profiles, file + env + flag merge
│   ├── errors.py                # error taxonomy mapped to exit codes
│   ├── logging.py               # structured logging + credential redaction filter
│   ├── models/                  # shared types, zero logic, no I/O
│   │   ├── target.py            #   TargetDescriptor, MetricSpace, Capabilities
│   │   ├── corpus.py            #   VectorBatch, CorpusView, SearchResult
│   │   ├── metrics.py           #   MetricResult, MetricState, Verdict
│   │   ├── report.py            #   Report, RunContext, schema_version
│   │   └── scene.py             #   ScenePayload, PointClass, LOD descriptor
│   ├── core/                    # all measurement logic; pure, importable standalone
│   │   ├── sampling.py          #   deterministic seeded sampling
│   │   ├── ground_truth.py      #   blocked BLAS exact k-NN oracle
│   │   ├── canary.py            #   recall_id / recall_dist against ground truth
│   │   ├── hubness.py           #   N_k histogram, hub share, anti-hubs, MAD outliers
│   │   ├── fragmentation.py     #   DFI, entry-point reachability checks
│   │   ├── partitions.py        #   IVF cell-size CV, HNSW in-degree distribution
│   │   ├── projection.py        #   deterministic incremental PCA to 3D
│   │   └── verdict.py           #   thresholds → MetricState → overall Verdict
│   ├── adapters/                # I/O only; read-only by construction
│   │   ├── base.py              #   IndexAdapter Protocol + shared helpers
│   │   ├── registry.py          #   URI scheme → adapter resolution
│   │   ├── synthetic_adapter.py #   in-memory NumPy reference adapter (P1)
│   │   ├── lancedb_adapter.py   #   PyArrow / Lance native reader (P5)
│   │   ├── qdrant_adapter.py    #   Qdrant HTTP/gRPC read APIs (P7)
│   │   └── pgvector_adapter.py  #   PostgreSQL read-only session (P7)
│   ├── pipeline.py              # orchestration: config + adapter → Report
│   ├── report/                  # rendering only; no computation
│   │   ├── json_report.py
│   │   ├── text_report.py       #   Rich terminal output
│   │   └── prometheus.py        #   textfile-collector format
│   ├── server/
│   │   ├── app.py               #   FastAPI factory, static mount, CORS off by default
│   │   ├── routes.py            #   REST + WebSocket progress stream
│   │   └── schemas.py           #   API-facing Pydantic v2 models
│   ├── synthetic/
│   │   ├── generator.py         #   corpus construction (clusters, dims, seeds)
│   │   └── pathologies.py       #   injectable churn / hub / imbalance operators
│   └── web/                     # Three.js SPA
│       ├── src/                 #   TypeScript sources (Vite)
│       ├── tests/               #   Vitest + Playwright
│       └── dist/                #   build output, bundled into the wheel by CI
└── tests/
    ├── unit/                    # pure functions, hand-computed fixtures
    ├── property/                # Hypothesis invariants
    ├── oracle/                  # optimised vs naive differential tests
    ├── contract/                # one suite every adapter must pass
    ├── integration/             # real engines via testcontainers, marked slow
    ├── e2e/                     # CLI golden files, exit codes, serve smoke
    ├── perf/                    # pytest-benchmark budgets, nightly only
    └── fixtures/                # generated corpora, golden reports
```

### Deltas from the source blueprint, and why

The upstream tree is preserved wherever it was sound. Five additions are load-bearing:

| Addition | Reason |
| :--- | :--- |
| `models/` | The blueprint put schemas in `server/schemas.py`. That makes `core/` depend on the web layer to describe its own results. Shared types move to a leaf package that everything may import and that imports nothing. |
| `core/ground_truth.py` split from `canary.py` | Ground truth is the oracle for canary recall **and** for hubness. Leaving it inside `canary.py` would force `hubness.py` to import `canary.py`, coupling two unrelated metrics. |
| `core/verdict.py` + `config.py` | Thresholds were implicit in the metric table. Externalising them is what makes calibration and baseline mode possible ([ADR-0011](adr/0011-thresholds-and-baseline-mode.md)) without touching metric code. |
| `report/` package | Separating rendering from `cli.py` lets the server reuse renderers and lets golden-file tests target renderers directly instead of shelling out. |
| `errors.py` + `logging.py` | The exit-code contract and credential redaction are cross-cutting invariants. They need one home each, not a convention. |

## 3. The adapter contract

This is the most important interface in the project. It is a `Protocol`, not a base class:
adapters are structurally typed, so a third party can satisfy it without importing our
class hierarchy, and `mypy --strict` verifies conformance at build time.

```python
# vhecfsck/adapters/base.py  (target shape — implemented in P1-02)

@runtime_checkable
class IndexAdapter(Protocol):
    """A read-only window onto a vector index.

    Every method is a pure read. No method may create, update, delete, lock,
    compact, vacuum, reindex, or otherwise mutate the target in any way.
    """

    @property
    def descriptor(self) -> TargetDescriptor:
        """Engine name, version, index kind, redacted target location."""

    @property
    def capabilities(self) -> Capabilities:
        """Which optional reads this engine supports. Drives UNAVAILABLE states."""

    @property
    def dimension(self) -> int: ...

    @property
    def metric_space(self) -> MetricSpace:
        """COSINE | L2 | DOT — read from the index, never assumed."""

    def counts(self) -> IndexCounts:
        """Live / deleted / total / indexed vector counts, as far as the engine knows."""

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        """Stream live vectors with stable IDs. Order need not be stable across calls."""

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        """Deterministic sample of live IDs. Same (n, seed, index state) → same result."""

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        """Random access by ID, for sampled subsets."""

    def search(self, queries: FloatMatrix, k: int, *, params: SearchParams) -> SearchResult:
        """The engine's own approximate search. This is the thing under test."""

    def partitions(self) -> PartitionStats | None:
        """IVF cell row counts. None if not an IVF index or not introspectable."""

    def graph_stats(self) -> GraphStats | None:
        """HNSW in-degree histogram and entry points. None if unavailable."""

    def close(self) -> None: ...
```

### Rules every adapter must obey

1. **No write methods exist.** Not disabled, not guarded — absent. There is nothing to
   accidentally call. A CI check greps adapter sources for engine write APIs
   (`delete`, `upsert`, `insert`, `optimize`, `VACUUM`, `REINDEX`, `commit`, …) and fails
   the build on a match outside a test file. See [ADR-0001](adr/0001-read-only-by-default.md).
2. **Capabilities are honest.** If an engine cannot report deleted counts, the adapter says
   so and the DFI metric becomes `UNAVAILABLE`. Returning `0` because the number is unknown
   is the single worst bug this project could ship.
3. **`search()` is never bypassed or tuned to flatter the engine.** Search parameters come
   from configuration and are echoed verbatim into the report, because a recall number
   without its `ef_search` / `nprobe` is meaningless.
4. **IDs are opaque, stable within a run, and sortable.** Normalised to `int64` where the
   engine allows it; string IDs are hashed to a dense index with the mapping kept
   adapter-side and never exported.
5. **Every adapter passes the shared contract suite** in `tests/contract/` unmodified. If a
   capability is unsupported, the suite verifies the `UNAVAILABLE` path instead of skipping.
6. **Credentials arrive from the environment, never from a report or log line.** The
   descriptor stores a redacted location string only.

## 4. Import dependency rules

Enforced mechanically by an `import-linter` contract in CI (`P0-06`), because a layering
rule that is only written down is a layering rule that is already broken.

```text
models/     ──▶ (nothing but stdlib, numpy, pydantic)
core/       ──▶ models/, numpy/scipy            ✗ never adapters, server, cli, report
adapters/   ──▶ models/, engine SDKs            ✗ never core, server, cli
synthetic/  ──▶ models/, numpy                  ✗ never core, adapters
report/     ──▶ models/                         ✗ never core, adapters
pipeline.py ──▶ models/, core/, adapters/, config
server/     ──▶ models/, report/, pipeline      ✗ never core directly
cli.py      ──▶ everything above
```

The consequence worth stating plainly: **`core/` is a standalone numerical library.** It
takes arrays and returns numbers. It can be tested with no database, no server, and no
mocks, which is what makes the quality bar in [`testing-strategy.md`](testing-strategy.md)
achievable.

## 5. Memory and compute strategy

Fixed by the ~1M × 768 single-node target ([ADR-0005](adr/0005-ground-truth-precision-and-blocking.md)).

- A 1M × 768 `float32` corpus is **3.07 GB**. It fits in RAM on a 16 GB machine, but not
  twice — so the pipeline holds exactly one materialised copy and views it, never copies it.
- Ground truth is a **blocked matmul**: stream corpus blocks of `B` rows (default sized to a
  ~256 MB working set), compute `Q × B` scores per block with BLAS `sgemm`, reduce with
  `argpartition`, and merge top-`k` across blocks. Peak extra memory is
  `Q × B × 4` bytes plus the block itself.
- Cosine spaces are handled by L2-normalising once at ingest and using dot products, with
  norms asserted to be within tolerance of 1 and zero-norm vectors reported rather than
  silently dropped.
- Accumulation precision is `float32` minimum. `float16` may be a *storage* format; it is
  never an accumulation format, because 768-term dot products in half precision reorder
  near-ties and corrupt the oracle.
- Everything expensive is bounded by `--max-seconds` and `--max-memory`, and degrades to
  documented sampling with a recorded confidence interval rather than an OOM kill.

## 6. Report schema and stability

The report is a versioned artifact consumed by CI systems and dashboards, so it is treated
as a public API from the first commit ([ADR-0008](adr/0008-report-schema-versioning.md)).

```jsonc
{
  "schema_version": "1.0",
  "tool_version": "0.1.0",
  "verdict": "FAIL",                  // OK | WARN | FAIL | INCONCLUSIVE
  "run": {
    "started_at": "…", "duration_seconds": 41.7,
    "seed": 1337, "host": {"cpu_count": 10, "blas": "…"},
    "deterministic": true
  },
  "target": {
    "engine": "lancedb", "engine_version": "…",
    "index_kind": "IVF_PQ", "metric_space": "cosine",
    "dimension": 768, "location": "file:///…/data.lance"   // redacted
  },
  "counts": {"live": 998231, "deleted": 41902, "total": 1040133, "indexed": 996100},
  "metrics": [
    {
      "id": "canary_recall",
      "state": "FAIL",                // OK | WARN | FAIL | UNAVAILABLE
      "value": 0.61,
      "unit": "ratio",
      "thresholds": {"warn": 0.85, "fail": 0.70, "direction": "lower_is_worse"},
      "sampling": {"queries": 200, "k": 10, "query_source": "corpus", "self_excluded": true},
      "detail": {"recall_id": 0.58, "recall_dist": 0.61, "ci95": [0.57, 0.65]},
      "evidence_strength": "medium",
      "explanation": "…", "remediation_hint": "…"
    }
  ],
  "warnings": ["snapshot_inconsistent: 12 ids vanished mid-audit"]
}
```

Stability rules: additive changes bump the minor `schema_version`; removals or semantic
changes bump the major and are accompanied by a migration note. Golden-file tests in
`tests/e2e/` fail on any unplanned change to the emitted structure.

## 7. Front-end architecture

- **Build**: Vite + TypeScript, Vitest for units, Playwright for smoke and visual
  regression. Typed and testable, which is the point ([ADR-0010](adr/0010-frontend-build-and-bundling.md)).
- **Shipping**: CI builds `web/dist` and bundles it into the wheel and the sdist. A user
  installing from PyPI needs **no Node toolchain**. A developer running from a git checkout
  gets a dev server proxying the FastAPI backend.
- **Rendering**: a single instanced/`Points` draw call over typed arrays. No per-point
  objects, no per-frame allocation.
- **Transport**: `ScenePayload` positions and classes travel as binary buffers, not JSON,
  with server-side level-of-detail decimation to a configurable display budget
  ([ADR-0009](adr/0009-scene-transport-and-lod.md)). 1M points as JSON is roughly 300 MB and
  is not a design.
- **Colour semantics** are part of the product, so they are fixed once and asserted by
  visual regression: cannibalising hubs red, anti-hubs blue, tombstones translucent grey,
  healthy vectors neutral, current query and its true neighbours highlighted.
- **The visualizer never computes a metric.** It renders a report. If it needs a derived
  value, the value is added to the schema.

## 8. Technology choices

| Concern | Choice | Note |
| :--- | :--- | :--- |
| Language / runtime | Python ≥3.11 | CI matrix 3.11 → 3.13; 3.14 tracked as advisory ([ADR-0002](adr/0002-packaging-and-toolchain.md)) |
| Packaging | `uv` + `hatchling` | Version single-sourced in `pyproject.toml` |
| Numerics | NumPy + system BLAS | SciPy only if a specific routine justifies it |
| Columnar I/O | PyArrow | Zero-copy path from Lance |
| CLI | Typer | Exit codes hand-managed, not delegated |
| Schemas | Pydantic v2 | Strict mode; used for the report and the API |
| Server | FastAPI + Uvicorn | Localhost-bound by default, no auth, no CORS |
| Front end | Three.js + TypeScript + Vite | |
| Lint / format | Ruff | Single tool, no Black/isort split |
| Types | mypy `--strict` on `core/`, `models/`, `adapters/` | Non-negotiable in the numeric core |
| Tests | pytest, Hypothesis, pytest-benchmark, testcontainers | Layers in [`testing-strategy.md`](testing-strategy.md) |
| Terminal output | Rich | Must degrade cleanly when not a TTY |

Dependency policy: the base install stays lean, and every engine SDK is an optional extra
(`vhecfsck[lancedb]`, `[qdrant]`, `[postgres]`, `[all]`). `uvx vhecfsck demo` must work with
the base install alone — the demo has no database dependency by design.
