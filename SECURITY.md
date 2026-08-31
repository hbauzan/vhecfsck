# Security Policy

## Read-only invariant

`vhecfsck` is a **strictly read-only** auditor for vector indexes.

It must never:

- write to, lock writers on, or mutate an audited target
- trigger compaction, optimize, reindex, or similar side effects
- issue `VACUUM`, `REINDEX`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, or `ALTER`
  against a target
- run remediation commands on the operator's behalf

This is enforced structurally (adapter protocol), statically (AST guards), at the
session level where engines allow it, and empirically in tests (`tests/integration/test_readonly_all.py`). See
[ADR-0001](roadmap/adr/0001-read-only-by-default.md) and [docs/read-only.md](docs/read-only.md).

**A hypothetical or observed write path is a security vulnerability**, not an
ordinary bug. Do not file it as a public GitHub issue.

Remediation advice that *prints* a command an operator could run is fine.
Executing that command from this tool is permanently out of scope.

## Supported versions

Pre-alpha. Report issues against `main`. Yank / support policy for published
releases will be documented when the first PyPI release ships.

## Private reporting channel

Report security issues — including any suspected violation of the read-only
invariant — via **GitHub private vulnerability reporting**:

https://github.com/hbauzan/vhecfsck/security/advisories/new

If that UI is unavailable, open a **private** contact with the repository owner
(`hbauzan`) and mark the subject clearly as `SECURITY`. Do not attach production
credentials; redact connection strings and tokens.

Please include:

1. A clear description of the behaviour (what wrote / what would write).
2. Steps to reproduce, and whether a target was mutated.
3. Affected commit SHA or package version, if known.
4. Impact assessment (data loss, compaction, lock contention, etc.).

We will acknowledge the report and coordinate disclosure. Ordinary bugs, false
positives, and feature requests belong in the public issue templates — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Supply Chain & Dependency Policy

`vhecfsck` enforces strict supply chain security standards for infrastructure environments:

- **Lean Base Footprint**: Direct runtime dependencies are restricted to `numpy`, `pydantic`, and `typer`. Engine SDKs are optional extras (`[lancedb]`, `[qdrant]`, `[postgres]`).
- **No Unapproved Dependencies**: Any new direct or transitive dependency requires an Architectural Decision Record (ADR) per Guardrail 2.
- **Lockfile Enforcement**: Root `uv.lock` and `vhecfsck/web/package-lock.json` are committed to guarantee reproducible builds.
- **Security Audits**:
  - Python: `uv run pip-audit` (or `pip-audit`).
  - Web UI: `npm audit --prefix vhecfsck/web`.
  - Workflow: `.github/workflows/security.yml` (`workflow_dispatch` trigger).
  - Dependabot: `.github/dependabot.yml` configured with grouped updates.
- **Release Software Bill of Materials (SBOM)**:
  - Release engineering (`P9-05`) generates an SPDX/CycloneDX SBOM using `syft` prior to release:
    ```bash
    uvx syft packages:. -o spdx-json=sbom.spdx.json
    ```
