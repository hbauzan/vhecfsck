# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Default `make verify` no longer re-enters pytest-cov from unit meta-tests
  (those stay `@slow` / `verify-full`). Coverage floors (80 overall / 90
  `core/`) are measured from a single instrumented run. `./setup.sh clean`
  only signals pytest processes whose command line includes this checkout.
- P1-08 scenario exit-code expectations calibrated to full-pipeline audit
  output (`drifted` → OK, `hubby` → INCONCLUSIVE, `tiny` canary → OK).
  Hubby hubness FAIL thresholds remain for P8 calibration.

### Added

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
