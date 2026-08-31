# Contributing Guide

Thank you for contributing to `vhecfsck`!

For full contributor panel setup, developer environment rules, and code verification instructions, please refer to the primary repository guide:

* [`CONTRIBUTING.md`](https://github.com/hbauzan/vhecfsck/blob/main/CONTRIBUTING.md)

---

## Single Quality Gate

`vhecfsck` uses a single quality gate (`make verify`) that runs linting, formatting, type-checking, test coverage, layering contracts, and read-only AST guards:

```bash
make verify
```

## Building Documentation Locally

To preview the documentation site locally:

```bash
uv sync --group docs
uv run python scripts/generate_cli_docs.py
uv run python scripts/generate_schema_docs.py
uv run python scripts/generate_metrics_docs.py
uv run mkdocs serve
```
