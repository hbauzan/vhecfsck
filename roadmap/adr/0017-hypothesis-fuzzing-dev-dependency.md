# ADR-0017 — Hypothesis as Dev Dependency for Core Fuzzing

**Status:** Accepted
**Affects:** P8 (P8-08), P9

## Context

Ticket P8-08 specifies hypothesis-driven fuzzing across every `core/` entry point, report schema deserialization, and binary/JSON scene codecs to detect unhandled exceptions, NaN leakage, or unexpected crashes when handling adversarial or extreme inputs.

Rule 2 requires an ADR for any new Python or front-end dependency.

## Decision

- Add **`hypothesis>=6`** to `dependency-groups.dev` in `pyproject.toml`.
- `hypothesis` is strictly a development and test dependency used by `tests/property/test_fuzz.py`. It is never required at runtime by end-users of the `vhecfsck` package.

## Consequences

**Buys:**
- Automated property-based fuzzing and shrinkage of failing test cases for numeric core, schema parsers, and scene codecs.
- Fulfills ticket P8-08's explicit contract for property-based adversarial testing.

**Costs:**
- Minor addition to dev dependencies in `pyproject.toml` and `uv.lock`.
