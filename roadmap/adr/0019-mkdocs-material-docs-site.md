# ADR-0019 — MkDocs Material for Documentation Site and Generated References

**Status:** Accepted
**Affects:** P9-02, CI/CD

## Context

Ticket `P9-02` requires building a static documentation site deployed to GitHub Pages. Hand-written reference documentation for CLI commands and Pydantic schemas drifts within releases. Therefore, CLI references (from Typer) and report schema references (from Pydantic v2) must be generated programmatically.

To build and serve the documentation site efficiently without polluting the base product wheel or product dependencies, documentation tools must be isolated into a dedicated `docs` dependency group.

## Decision

- **Use `mkdocs` and `mkdocs-material`** for building static documentation and deploying to GitHub Pages.
- **Isolate documentation tools** into `dependency-groups.docs` in `pyproject.toml` (`mkdocs`, `mkdocs-material`, `mkdocstrings[python]`).
- **Generate CLI and Schema references programmatically** via Python scripts (`scripts/generate_cli_docs.py`, `scripts/generate_schema_docs.py`, `scripts/generate_metrics_docs.py`) executed before `mkdocs build`.
- **Enforce dead-link checking** in CI to guarantee zero broken links across published documentation pages.

## Consequences

**Buys:**
- Fast, accessible static documentation site with search, code highlighting, and mobile responsiveness.
- Programmatic reference documentation that stays 100% synchronized with Typer CLI definitions and Pydantic v2 models.
- Zero footprint on production wheels or base `pip install vhecfsck` runtime.

**Costs:**
- `mkdocs-material` and dependencies in `dependency-groups.docs` must be synchronized during docs build tasks (`uv sync --group docs`).

## Revisit if

- Documentation generation scripts require incompatible MkDocs plugin hooks.
- Static site hosting migrates away from GitHub Pages.
