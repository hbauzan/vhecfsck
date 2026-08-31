# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- HYG-03: Fixed commented `--all-extras` recipe in `security.yml` and added workflow lint test; moved module-level `importorskip` out of Qdrant integration tests so `pytestmark` deselects them cleanly; updated `hatch_build.py` hook to skip npm execution when `dist/index.html` exists and included `hatch_build.py` in sdist `only-include`; removed unmeasured wheel size numbers from phase 4 roadmap; and updated `test_spa_static_serving` to cover both pre-built and missing bundle paths.
- HYG-02: Declared `[server]` optional dependencies (`fastapi`, `uvicorn`) in `pyproject.toml` and `dev` group, implemented custom hatch build hook in `hatch_build.py` to bundle SPA assets into wheel and sdist, and updated serve missing extra test to run in an isolated process.

### Changed

- HYG-01: Synced roadmap documentation, README status, capability matrix, and ADR-0010 to main; isolated Qdrant and Postgres server integration test modules with `pytest.mark.integration`.

### Added

- P7-07 cross-engine hubness suite: same `SeedSpec` on synthetic, LanceDB, Qdrant, and pgvector; hub share / anti-hub agree (delta 0 on the measured corpus). Table: `docs/engines/cross-engine.md`.
- P7-03 filtered / group-by canary recall (`--filter` / `--group-by`) with per-group `canary_groups` on the report (schema 1.1). Qdrant opts into `filtered_search`. Scenario: `docs/scenarios/qdrant-7147.md`.
- P7-05 reproduce `pgvector#244`: harness seeds HNSW + dead-tuple churn with autovacuum off; canary FAIL / DFI FAIL recover after operator `VACUUM`. Docs: `docs/scenarios/pgvector-244.md`.
- P8-11 Supply chain and dependency review: configured on-demand security audit workflow (`.github/workflows/security.yml`) for `pip-audit` and `npm audit`, grouped Dependabot configuration (`.github/dependabot.yml`), committed Web UI lockfile (`vhecfsck/web/package-lock.json`), documented SBOM release command in `SECURITY.md`, and validated dependency footprint against Guardrail 2.
- P8-09 Error message audit: table-driven error message test suite (`tests/e2e/test_error_messages.py`) dynamically auditing all `VhecfsckError` subclasses to enforce non-empty distinct human hints, unique machine codes, valid exit codes, descriptive `UNAVAILABLE` reasons, and credential redaction safety. Added default hints to error taxonomy classes in `vhecfsck/errors.py`.
- P7-08 Engine guides and capability matrix: published Qdrant engine guide (`docs/engines/qdrant.md`), pgvector engine guide (`docs/engines/pgvector.md`), and consolidated capability matrix (`docs/engines/capability-matrix.md`) detailing metric exactness, proxy estimates, and feature availability per engine. Updated `README.md` with `uv` extra installation commands and capability matrix links.
- P7-06 HNSW graph statistics evaluation: documented unavailability of HNSW graph introspection APIs for Qdrant (v1.19.0) and pgvector (0.8.x) in `docs/engines/graph-stats.md`, and wired `adapter.graph_stats()` entrypoint_tombstoned escalation to DFI `FAIL` in the audit pipeline.
- P7-01 container integration harness: session-scoped `testcontainers` fixtures for Qdrant and PostgreSQL+pgvector, pinned image tags, health-gated startup, and a shared deterministic seeder in `tests/` (ADR-0018: `testcontainers` in the `dev` group, not a product extra). On-demand: `uv run pytest tests/integration -q --no-cov`.
- P8-08 hypothesis property-based fuzzing test suite (`tests/property/test_fuzz.py`) covering numeric core entry points, 3D projection, report schema deserialization, and binary scene codec. ADR-0017: `hypothesis` as a dev dependency.
- Phase 7 Qdrant and pgvector adapters (P7-02 / P7-04): read-only `QdrantAdapter`
  (`qdrant://`, local/embedded `:memory:` and `path=`) with honest deleted-count
  capabilities (segment telemetry only — never `points_count` vs
  `indexed_vectors_count`), and read-only `PostgresAdapter` (`postgres://` /
  `postgresql://`) with server-enforced `default_transaction_read_only`, catalog
  introspection, and an EXPLAIN guard against sequential scans. Optional extras
  `[qdrant]` (`qdrant-client`) and `[postgres]` (`psycopg[binary]`, `pgvector`)
  are declared (ADR-0016). Tests: `tests/unit/test_qdrant_adapter.py`,
  `tests/unit/test_postgres_adapter.py`, `tests/integration/test_qdrant_*.py`,
  `tests/integration/test_postgres_*.py`.

### Changed

- `make verify` runs the default pytest suite once (via `coverage`). `make test`
  stays as the uninstrumented inner loop. Playbook / `AGENTS.md`: three moments
  (TDD while coding → verify once per ticket → `verify-full` on a version tag).
- Dev-protocol pack: product handoff memory lives in `roadmap/lessons-learned.md`
  (pack keeps only the template). `AGENTS.md` opt-out is first-class. Delivery
  is local commits free, squash to one conventional commit, merge to `main` on
  explicit OK. Skill templates no longer `uv sync --all-extras` or double
  pytest-cov. Protocol WARN exit is `8` / `0`+stderr; the CLI stays on
  ADR-0004 (`1` = `WARN`). Follow-ups: `roadmap/dev-protocol-followups.md`.

- GitHub-hosted Actions (`ci.yml`, `nightly.yml`) disabled permanently so private-repo
  runner minutes stay at zero. The quality gate is local `make verify`. Linux matrix
  in Docker is post-launch TBD (`P9-10`).
- Default `make verify` no longer re-enters pytest-cov from unit meta-tests
  (those stay `@slow` / `verify-full`). Coverage floors (80 overall / 90
  `core/`) are measured from a single instrumented run. `./setup.sh clean`
  only signals pytest processes whose command line includes this checkout.
- P1-08 scenario exit-code expectations calibrated to full-pipeline audit
  output (`drifted` → OK, `hubby` → INCONCLUSIVE, `tiny` canary → OK).
  Hubby hubness FAIL thresholds remain for P8 calibration.

### Added

- Phase 6 Visualizer Depth (P6-01..P6-09): progressive LOD chunking for 1M-point corpora
  (`GET /api/scene?budget=&chunk=`), live audit progress (`WS`/`GET /api/progress`),
  interactive query probe (`POST /api/probe`) with hub cannibalisation, colour-by
  partition/nk/distance views and canvas histograms, tombstone layer that never
  fabricates positions, report-derived camera presets and a frame-deterministic
  guided tour, `make demo-gif` README capture, deuteranopia palette plus marker/size
  encoding, and expanded visual regression coverage. The SPA still computes no metric.

- Phase 5 LanceDB Adapter (P5-01..P5-10 complete): Read-only `LanceDBAdapter` for Lance / LanceDB datasets (`vhecfsck/adapters/lancedb_adapter.py`). Features dataset discovery and descriptor construction (P5-01), immutable snapshot version pinning `--dataset-version N` (P5-02), exact per-fragment deletion accounting (P5-03), vector streaming scan and random access `_rowid` lookup with float16-to-float32 upcasting (P5-04), native k-NN batched search with `nprobe`/`refine_factor` effective parameter propagation (P5-05), IVF cell partition introspection (P5-06), generic read-only verification harness with SHA-256/mtime tree snapshotting and `chmod -R a-w` read-only mount verification (`tests/integration/test_readonly_lancedb.py`, P5-07), version compatibility matrix checking with one-time runtime warning (P5-08), automated reproduction test for `lancedb/lance#4164` unindexed appended data pathology (`tests/integration/test_repro_lance_4164.py`, `docs/scenarios/lance-4164.md`, P5-09), and LanceDB user guide documentation (`docs/engines/lancedb.md`, P5-10).

- Phase 4 SPA Front-End Visualizer (`vhecfsck/web/`): Vite + TypeScript scaffold,
  zero-copy binary scene decoder, Three.js point-cloud renderer with translucent tombstone
  pass, audit report HUD overlay with 3D projection variance caveat, Vitest unit tests,
  and static bundle mounting for `vhecfsck serve` (P4-07..P4-11).

- Embedded 3D visualizer server `vhecfsck serve --target <uri> [--port 8765] [--host 127.0.0.1] [--no-browser] [--report PATH]` and `--serve` flag integration, featuring streaming incremental PCA 3D projection with `svd_flip` determinism (`vhecfsck.core.projection`), class-stratified and voxel-grid Level-of-Detail decimation (`vhecfsck.core.lod`), `ScenePayload` domain model (`vhecfsck.models.scene`), application/octet-stream 8-byte aligned binary scene transport codec (`vhecfsck.report.scene_codec`), and single-flight FastAPI server (`vhecfsck.server`). Tickets: P4-01, P4-02, P4-03, P4-04, P4-05, P4-06.
- Exit-code contract test suite in `tests/e2e/test_exit_codes.py` exercising real CLI subprocesses for all documented exit codes (0, 1, 2, 3, 4, 70 via `_VHECFSCK_FAULT_INJECT=1`), non-interactive behavior, and quiet mode. Ticket: P3-08.
- Export CLI command `vhecfsck export --report PATH [--format text|json|prometheus|markdown]` in `vhecfsck/cli.py` and GitHub Flavored Markdown renderer in `vhecfsck/report/markdown.py` (`render_markdown`) for PR comments and job summaries, with major schema version rejection and end-to-end tests in `tests/e2e/test_cli_export.py`. Ticket: P3-07.
- Prometheus exporter test suite in `tests/e2e/test_prometheus.py` for `vhecfsck/report/prometheus.py` (`render_prometheus`), validating textfile-collector series, metric state/unavailable gauges, bounded label cardinality, and `promtool check metrics` compliance. Ticket: P3-06.
- Demo CLI command `vhecfsck demo [--scenario NAME] [--size small|large] [--serve]` in
  `vhecfsck/cli.py`, running zero-dependency synthetic audits (default scenario `tombstoned`
  reproducing `pgvector#244` with FAIL verdict exit code 2). Unlocks `./setup.sh demo` Forty-two
  contributor action and includes end-to-end tests in `tests/e2e/test_cli_demo.py`. Ticket: P3-05.
- Primary CLI command `vhecfsck audit --target <uri> [options]` in `vhecfsck/cli.py`,
  supporting options `--format text|json|prometheus`, `--output PATH`, `--queries`, `--k`,
  `--hubness-sample`, `--k-hub`, `--hubness-source`, `--seed`, `--nprobe`, `--ef-search`,
  `--max-seconds`, `--max-memory-mb`, `--strict-unavailable`, `--only`, `--skip`, `--config`,
  `--no-progress`, and exit code taxonomy mapping (0=OK, 1=WARN, 2=FAIL, 3=INCONCLUSIVE, 4=USAGE).
  Includes Prometheus exporter renderer in `vhecfsck/report/prometheus.py` (`render_prometheus`)
  and end-to-end tests in `tests/e2e/test_cli_audit.py`. Ticket: P3-04.
- Rich terminal renderer in `vhecfsck/report/text_report.py` (`render_terminal`),
  featuring target identity header, overall verdict banner, index cardinalities,
  metrics table, metric explanations/hints, offending vector details, and warnings.
  Supports clean plain-text output when `color=False` (piped stdout/NO_COLOR) and
  end-to-end tests in `tests/e2e/test_text_output.py`. Ticket: P3-03.
- Deterministic JSON renderer in `vhecfsck/report/json_report.py` (`render_json`,
  `generate_report_schema`), published schema `schema/report-1.0.json`, golden reference
  fixtures in `tests/fixtures/golden/`, and schema drift prevention tests in
  `tests/e2e/test_json_golden.py`. Ticket: P3-02.
- Pydantic v2 Report schema in `vhecfsck/models/report.py` (`Report`, `RunContext`
  BaseModels with `extra="forbid"`, `SCHEMA_VERSION = "1.0"` per ADR-0008, secret
  leak prevention validator, and `Report.compare` structured diff for baseline mode).
  Accepted `pydantic>=2.0` in base dependencies per ADR-0002. Ticket: P3-01.

- Audit pipeline in `vhecfsck/pipeline.py` (`run_audit`: validate → metrics →
  verdict → `Report`) with per-stage timings, metric isolation, corpus
  materialisation once, and injectable ground-truth backend. Ticket: P2-10.
- Report types in `vhecfsck/models/report.py` (P3-01 precursor dataclasses).
- Hubness metrics in `vhecfsck/core/hubness.py` (`hub_share_top1pct`,
  `antihub_fraction`, independent subsample per ADR-0006 / CORRECTION 3,
  §3.5 diagnostics, truth and engine counting paths). Ticket: P2-06.
- Verdict engine in `vhecfsck/core/verdict.py` (`evaluate`, `aggregate`,
  `verdict_to_exit_code`) with exhaustive §6 truth table. Ticket: P2-09.
- IVF partition-size CV in `vhecfsck/core/partitions.py` (population `ddof=0`,
  Fixture C, companion diagnostics). Ticket: P2-08.
- Deletion fragmentation index in `vhecfsck/core/fragmentation.py` (`dfi`,
  CORRECTION 1 UNAVAILABLE path, fragment breakdown, entrypoint escalation).
  Ticket: P2-07.
- Metric result model in `vhecfsck/models/metrics.py`: `MetricState` (severity
  ordered OK < WARN < FAIL), `Verdict`, `EvidenceStrength`, `Direction`,
  `ThresholdSpec` (inverted-pair rejection), `MetricResult` with ADR-0004
  constructor invariants, JSON round-trip helpers. Ticket: P2-01.
- Canary recall in `vhecfsck/core/canary.py` (`recall_id` / tie-tolerant
  `recall_dist`, bootstrap CI95, §2.5 edge diagnostics). Fixture A locked;
  true distances recomputed from corpus (ADR-0007). Ticket: P2-05.
- Blocked BLAS exact k-NN in `vhecfsck/core/ground_truth.py` (`exact_knn`,
  `KnnResult`, float64 cross-check): working-set-derived blocks, L2
  clamp-before-sqrt, float16 upcast, block-size invariance vs naive oracle.
  Ticket: P2-04.
- Naive oracle under `tests/oracle/` (`naive_knn`, `naive_recall`, `naive_nk`,
  `naive_cv`) with Fixture A/B/C self-checks; deliberately unoptimised;
  import-linter forbids `vhecfsck` → `tests.oracle`. Ticket: P2-03.
- Named synthetic scenarios (`healthy`, `drifted`, `tombstoned`, `hubby`,
  `capability_limited`, `tiny`) with frozen exit-code expectations; `open_scenario`
  in adapters (layering: synthetic returns ``ScenarioSpec`` only). Ticket: P1-08.
- Shared adapter contract suite (`tests/contract/`) parametrised over
  SyntheticAdapter modes; capability honesty (None → UNAVAILABLE) tested, not
  skipped. Documented in CONTRIBUTING as the definition of a working adapter.
  Ticket: P1-07.
- Adapter registry (`register` / `resolve_class` / `open_target`) for
  `synthetic://`, `lance://` (and bare `*.lance` paths), `qdrant://`,
  `postgres://`. Lazy SDK import with install hints; credentials redacted in
  errors. Ticket: P1-06.
- `SyntheticAdapter` (`exact` / `ivf` / `ivf_tombstoned`) with private seeded
  k-means, tombstone post-filter (`ef_search` as ef_budget), honest
  capabilities (`report_graph_stats=False`), counts from pathology
  annotations, and optional `.npz` session persistence. Documented recall
  collapse triple: delete_fraction=0.35, ef_budget=8, nprobe=1. Ticket: P1-05.
- Shared domain types in `vhecfsck/models/` (`MetricSpace`, `IndexKind`,
  `TargetDescriptor`, `Capabilities`, `IndexCounts`, `VectorBatch`,
  `SearchResult`, `PartitionStats`, `GraphStats`). Leaf package: validation
  only, no I/O or metric logic; `TargetDescriptor.location` expects a string
  already passed through `redact_secrets`. Ticket: P1-01.
- `IndexAdapter` `@runtime_checkable` Protocol plus `SearchParams` and shared
  helpers (`l2_normalize`, `StringIdMapper`, `iter_vector_batches`) in
  `vhecfsck/adapters/base.py`. No write methods; optional reads return `None`.
  Ticket: P1-02.
- Seeded synthetic corpus generator (`generate_corpus`) with controllable
  cluster-size skew, cosine unit norms, DOT norm distribution, float32-only
  blocked generation, and recorded `CorpusSpec`. Ticket: P1-03.
- Injectable pathologies (`apply_churn`, `inject_hubs`, `inject_antihubs`,
  `skew_partitions`) returning pure `CorpusState` updates plus
  `GroundTruthAnnotation` for oracle tests. Ticket: P1-04.
- Package bootstrap: installable `vhecfsck` with hatchling, version single-sourced
  from `pyproject.toml`, console script entry point, and empty optional extras
  (`lancedb`, `qdrant`, `postgres`, `server`, `dev`, `all`). Ticket: P0-01.
- Contributor `setup.sh` (macOS): Hitchhiker menu, `uv sync`, adaptive
  `verify` / `demo` / `serve`. Not a daemon and not a SaaS panel. Ticket: P0-15.
- Lint/format/typing toolchain: `ruff` (select E,F,W,I,N,UP,B,A,C4,SIM,ARG,PTH,RUF;
  ANN+D on `core/` and `models/`) and `mypy` (`strict` on `core`/`models`/
  `adapters`, lenient on tests). Ticket: P0-02.
- Apache-2.0 `LICENSE` and `NOTICE` attributing copyright to `hbauzan`
  (redistribution must retain attribution).
- Test harness: pytest `--strict-markers` / `--strict-config` / `-ra`, registered
  markers (`slow`, `integration`, `perf`, `requires_*`), default exclusion of
  slow/integration/perf, `pytest-cov` with overall `fail_under=80` (core-scoped
  `fail_under=90` via separate invocation), `tests/conftest.py` seeded `rng` +
  `deterministic_env`, and the architecture test directory skeleton. Ticket: P0-03.
- Single quality gate: root `Makefile` with `make verify` (lint, format-check,
  typecheck, test, coverage, layers stub) plus `verify-full`, `fmt`, `test-fast`,
  `clean`, `web-build`, `demo`. Ticket: P0-04.
- Error taxonomy: `ExitCode` and `VhecfsckError` hierarchy (`UsageError`,
  `TargetConnectionError`, `CapabilityError`, `InconclusiveError`, `InternalError`)
  with a single uncaught-exception handler. Ticket: P0-05.
- `AuditConfig` with metrics-spec default thresholds, file/env/CLI precedence, and
  unknown-key rejection. Ticket: P0-07.
- Structured logging with mandatory `RedactionFilter` (stderr diagnostics;
  `--log-format human|json`, `-v`/`-vv`/`--quiet`). Ticket: P0-06.
- Community docs: README placeholder (with `TODO(P9-01)` GIF slot), CONTRIBUTING
  (licence-header policy), CODE_OF_CONDUCT, SECURITY (read-only + private
  reporting), GitHub issue/PR templates. Ticket: P0-11.
- Import-layering via `import-linter` (`.importlinter`) wired into `make verify`
  `layers` target; `report/` and `server/` package scaffolds. Ticket: P0-08.
- Read-only AST guard (`scripts/check_readonly.py`) for adapters/ and core/,
  wired into `make verify`. Ticket: P0-09.
- GitHub Actions CI (`ci.yml` matrix + advisory 3.14) and `nightly.yml`
  (`make verify-full` + engine-SDK drift placeholder). Ticket: P0-10.
- Root `AGENTS.md` distilled from the agent playbook (gate, hard guardrails,
  delivery). Ticket: P0-12.
- Canonical package URLs in `pyproject.toml`; naming tests; ADR-0012 reservation
  notes (GitHub private; PyPI claim pending owner token). Ticket: P0-13.
- Pre-commit hooks (ruff, hygiene, private-key detection, read-only guard).
  Ticket: P0-14.
