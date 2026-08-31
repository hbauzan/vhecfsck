# Testing Strategy & Quality Gates

This document outlines the testing architecture, quality gates, and mutation testing suite for `vhecfsck`.

## Quality Gates

- **`make verify`**: The single quality gate required for every ticket. Runs linting (`ruff`), formatting check, static type checking (`mypy`), unit & integration tests, coverage gates (≥80% repository-wide, ≥90% core), import layering checks (`lint-imports`), and read-only AST checks (`check_readonly.py`).
- **`make verify-full`**: Runs `make verify`, slow/perf/integration suites, and core mutation testing.

## Mutation Testing (`P8-07`)

Mutation testing assesses test suite effectiveness by verifying that artificial mutations in core numeric and verdict logic cause tests to fail.

### Scope
- **Target module**: `vhecfsck/core/verdict.py` and numeric threshold evaluation.
- **Suite**: `tests/unit/test_mutation_core.py` (runnable via `make mutation`).
- **Invariants**:
  - Comparison operators (`LOWER_IS_WORSE` vs `HIGHER_IS_WORSE`, `warn` vs `fail` bounds) must trigger exact state changes (`OK`, `WARN`, `FAIL`).
  - Low-evidence failures are capped at `WARN`.
  - Strict vs non-strict `UNAVAILABLE` handling correctly defaults to `INCONCLUSIVE` or `FAIL`.
  - 0 surviving mutants are tolerated in core verdict and threshold boundary logic.
