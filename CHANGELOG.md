# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Documentation

- GitHub Pages home shows the current release (derived from `pyproject.toml` at docs-build time) and publishes the root changelog. Leaf Pages URLs are the form without a trailing slash (`/changelog`, not `/changelog/`).

## [0.1.3] - 2026-09-02

### Improved

- TH-05 Vectorised the synthetic IVF k-means build (`vhecfsck/adapters/synthetic_adapter.py`), which instrumentation showed to be 180.30s of the 284.59s default suite across 90 `_fit_ivf` calls. The row-chunked broadcast panel (`_distance_panel`), `np.argmin` assignment and `np.bincount` + `np.add.at` centroid update are **bit-exact** against the loop they replace, so no golden report fixture was regenerated. Pinned by a differential test (`tests/oracle/test_ivf_build.py`) asserting byte equality of `centroids`, `assignment` and every list against the loop reference preserved in `tests/oracle/reference_ivf.py`, over L2/COSINE/DOT, the `n < n_lists` centroid-padding branch and band-size invariance. The GEMM identity `|q|^2 + |c|^2 - 2qc` is explicitly rejected (1.95e-3 error) and the reason is recorded in the code. Measured on Apple Silicon / Python 3.11.15 / numpy 2.4.6: default suite 284.59s to 76.99s.
- `SyntheticAdapter.from_npz` no longer pays a full k-means fit only to discard it: the persisted build is passed in through the new `prebuilt_ivf` argument instead of overwriting private attributes after construction.
- Contributor console (`setup.sh`): updated option descriptions, added ANSI progress bar rendering, autocurative virtual environment synchronization (`uv sync --group dev --extra lancedb`), and full non-interactive verb support (`sync`, `verify`, `demo`, `serve`, `clean`, `dump`).

### Documentation

- MI-03 / MI-04 / MI-06 Retracted published claims that were not backed by a measurement. `docs/calibration/thresholds.md` now separates **Measured FPR** from **Measured FNR**: `hub_share_top1pct`, `antihub_fraction` and `partition_size_cv` have no pathological positive anywhere in the reference calibration, so their detection sensitivity is marked unvalidated instead of being published as `FPR / FNR: 0.0%`. The scenarios named for those pathologies do not move them (`synthetic-hubby` reports `hub_share 0.0877 OK`; `synthetic-drifted`, the `lance#4164` scenario, reports `partition_size_cv 1.0342 OK`). `docs/calibration/README.md` gains a "Known gaps" section and explains that the stale `WARN`/`FAIL` verdict columns in `results.csv` predate the per-dimension profiles while its **values** remain the calibration data. ADR-0006's attribution of the 0.25/0.40 thresholds to "the hubness literature" is struck and replaced with the actual reference (Radovanović, Nanopoulos & Ivanović, JMLR 11:2487-2531, 2010, which measures skewness of `N_k` and publishes neither threshold); its status records that the threshold rationale is superseded by ADR-0011/P8-02. `roadmap/02-metrics-spec.md` now cites ANN-Benchmarks (Aumüller, Bernhardsson & Faithfull, *Information Systems* 87, 2019) for `recall_dist` rather than presenting it as a house correction, cites Efron (1979) for the percentile bootstrap, and declares the deviation that widens the confidence interval to contain the mean — previously only a code comment in `vhecfsck/core/canary.py`. No metric code changed.
- Rewrote `roadmap/plan_optimizacion_test_harness.md` against instrumented evidence. TH-01, TH-02 and TH-03 are **cancelled**, not deferred: `exact_knn` already uses BLAS and the proposed GEMM identity is not bit-exact, the `coverage.py` C tracer was already active (`CTracer available: YES`), and shrinking fixtures to `size="tiny"` is forbidden by lesson 37 and guardrail 1. Added TH-06 (`_merge_query_topk` at large Q), TH-07 and TH-08.
- Added `roadmap/plan_integridad_matematica.md` and the MI backlog section: `inject_hubs` measurably fails to move `hub_share` (0.0882 to 0.0864 as hubs go from 8 to 800) while `scenarios.py` asserts `OK` for both hubness metrics; ADR-0006's attribution of the 0.25/0.40 thresholds to "the hubness literature" is refuted against Radovanović et al. (JMLR 11:2487-2531, 2010); `docs/calibration/` publishes an FNR with no pathological positive behind it; `S_Nk` is missing; and `recall_dist` is the published ANN-Benchmarks definition (Aumüller et al., *Information Systems* 2019) rather than the repo's own correction. Findings only — no metric code was touched.
- Recorded the release process as it actually stands in `docs/releasing.md`: the automated tag-triggered pipeline has never executed (no `v*` tag has ever existed), and `0.1.0` through `0.1.3` were published manually. Activating the documented path is P9-12.

### Infrastructure

- Re-enabled `.github/workflows/ci.yml` on `ubuntu-latest` across Python 3.11/3.12/3.13. It had been disabled on 2026-08-30 because "runners are billed on this private repo"; the repository is public now and standard GitHub-hosted runners are free in public repositories. This closes the only platform gap in the gate, which otherwise runs on macOS/arm64 only. The CI sync is `uv sync --group dev --group docs --extra lancedb` — `--group dev` alone goes red, because the LanceDB integration modules import `pyarrow` at import time (pytest imports a module to collect it before markers deselect it) and the docs generation test shells out to `mkdocs build --strict` with no skip guard. Artifacts carry `retention-days: 7`.
- Filed P9-11 (bump GitHub Actions off the deprecated Node 20 runtime) and P9-12 (activate PyPI Trusted Publishing with a protected `pypi` environment) in `roadmap/backlog.md`.

## [0.1.2] - 2026-09-01

### Fixed

- Updated README hero GIF asset generator (`scripts/record_demo.py`) with frequency-based unique palette sampling and complete WebGUI UI layout rendering.
- Added raw GitHub CDN URLs for hero GIF asset in `README.md` and `docs/index.md` for PyPI (`https://pypi.org/project/vhecfsck/`) and GitHub Pages compatibility.
- Added PNG fallback asset export (`docs/assets/vhecfsck-demo.png`).

## [0.1.0] - 2026-09-01

### Added

- P9-08 Post-launch triage window: created GitHub issue templates (`bug_report.md`, `feature_request.md`, `false_positive_report.md`) in `.github/ISSUE_TEMPLATE/` and published post-launch FAQ in `docs/faq.md`.
- P9-07 Launch execution: validated tag release readiness (`v0.1.0`), launch post content, clean-machine quickstart verification, and community announcement readiness.
- P9-06 Pre-launch review pass: completed repository-wide audit for secrets (0 committed), documentation links (0 broken on strict build), license compliance (Apache-2.0/MIT compatible), clean-environment demo execution, and code quality (0 TODO/FIXME markers in shipped code).
- P9-05 Release engineering: created GitHub Actions release workflow (`.github/workflows/release.yml`) for packaging wheel/sdist distributions, executing clean-container smoke tests, publishing to PyPI via Trusted Publishing OIDC, and creating GitHub Releases with build artifacts. Documented release guide in `docs/releasing.md`.
- P9-04 Anchor issues re-verification & launch post: re-verified upstream anchor issues (`pgvector#244`, `lance#4164`, `qdrant#7147`) on 2026-09-01, updated `roadmap/00-vision-and-scope.md`, and published launch blog article in `docs/blog/silent-recall-decay.md`.
- P9-03 CI integration recipes: created copy-pasteable integration recipes for GitHub Actions composite action (`.github/actions/vhecfsck/action.yml`), test workflow (`.github/workflows/test-composite-action.yml`), GitLab CI (`examples/gitlab-ci.yml`), Kubernetes CronJob (`examples/k8s-cronjob.yaml`), crontab (`examples/crontab.example`), Apache Airflow DAG (`examples/airflow_dag.py`), and Dagster job (`examples/dagster_job.py`). Updated `docs/ci-integration.md` with GitHub Step Summary markdown export usage and Prometheus alerting rules with staleness alerts (`vhecfsck_metric_unavailable`). Added unit test suite (`tests/unit/test_ci_recipes.py`).
- P9-02 Documentation site: configured MkDocs Material site (`mkdocs.yml`), GitHub Actions Pages workflow (`.github/workflows/docs.yml`), ADR-0019 (`roadmap/adr/0019-mkdocs-material-docs-site.md`), and programmatic generators for Typer CLI reference (`scripts/generate_cli_docs.py`), Pydantic v1.1 report schema reference (`scripts/generate_schema_docs.py`), and normative metrics reference with spec citations (`scripts/generate_metrics_docs.py`). Enforced zero warnings on `mkdocs build --strict` and automated unit test suite (`tests/unit/test_docs_generation.py`).
- P9-01 README: published the launch-ready `README.md` featuring the hero GIF asset (`docs/assets/vhecfsck-demo.gif`), one-line quickstart (`uvx vhecfsck demo`), problem statement linking anchor issues (`qdrant#7147`, `pgvector#244`, `lance#4164`), explicit technical limitations, 5-metric threshold table, exit code taxonomy & CI recipe, engine capability matrix, read-only & zero egress guarantees, measured reference performance numbers, and install instructions with extras.
- Diagnóstico y mitigación de procesos pytest/Python huérfanos: script ejecutable nativo sin dependencias externas (`scripts/clean_orphans.py`) para terminación de procesos huérfanos acotados al repositorio actual, integración con target defensivo y pre-flight check `clean-proc` en `Makefile` (dentro de `verify`, `test` y `coverage`), registro de handlers de señales `SIGTERM`/`SIGHUP` en `tests/conftest.py` para salida inmediata ante interrupción de subprocesos, y límites defensivos de hilos numéricos (`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`) para prevenir saturación de CPU multi-núcleo.
- P8-04 Performance budgets and scale benchmarks: published reference machine specs (Apple Silicon arm64, macOS, Python 3.11.15) and empirical timing/peak RSS benchmark table in `docs/performance.md`, created benchmark measurement script (`scripts/measure_perf.py`), and added performance budget assertion test suite (`tests/perf/test_performance_budgets.py`) asserting wall-clock and RSS bounds across 100k/1M Ground Truth, S=20k Hubness, 1M 3D Projection, full audit, and binary scene payload codec, including a test verifying budget assertion failure on a 2x slowdown.
- P8-03 Baseline and delta mode: added `vhecfsck audit --baseline baseline.json [--gate absolute|delta|both]` and `vhecfsck baseline record --output baseline.json` commands. Implemented strict comparability checks (seed, k, hubness_sample_size, k_hub, metric_space, dimension, engine) emitting `not_comparable` with exit code 3 (`INCONCLUSIVE`) on mismatch. Extended `AuditConfig` with calibrated `DEFAULT_DELTA_THRESHOLDS` and `Report` schema with optional `baseline_delta` payload.
- P8-02 Calibrated default thresholds and per-dimensionality profiles: introduced dimension-aware threshold profiles (`low`, `medium`, `high`, `ultra_high` in `vhecfsck/config.py`) based on empirical P8-01 Gaussian control measurements to prevent false positives on high-dimensional vector spaces ($d \ge 128$), updated `vhecfsck/pipeline.py` to resolve dimension-calibrated defaults automatically while preserving explicit user overrides, published calibrated error rate documentation (`docs/calibration/thresholds.md`), and amended ADR-0011 status and findings.
- P8-01 Reference dataset calibration harness: reproducible harness (`scripts/calibrate.py`, `make calibrate`) executing the full metric suite over isotropic Gaussian controls across dimensions d ∈ {64, 128, 384, 768, 1536}, named synthetic scenario pathologies (`healthy`, `drifted`, `tombstoned`, `hubby`), and public ANN benchmark datasets (`sift-128`, `gist-960`, `glove-100`, `sentence-minilm`). Enforces permissive dataset licensing and excludes LDC-restricted corpora (`nytimes-256`, risk R13). Generates derived calibration statistics (`docs/calibration/results.csv`, `hubness_sensitivity.csv`, `skipped.csv`), catalogue documentation (`docs/calibration/datasets.md`), and hubness sampling sensitivity curves across `S` ∈ {1k, 5k, 20k, 50k} and `k_hub` ∈ {5, 10, 20}. Tests: `tests/unit/test_calibration_harness.py`, `tests/perf/test_calibration.py`.

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
