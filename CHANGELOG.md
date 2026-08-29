# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
