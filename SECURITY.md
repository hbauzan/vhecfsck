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
session level where engines allow it, and empirically in tests. See
[ADR-0001](roadmap/adr/0001-read-only-by-default.md).

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
