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
