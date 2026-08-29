# Contributing

Thanks for helping. `vhecfsck` is a **read-only CLI auditor** for vector indexes.
The product surface is `uvx vhecfsck` (and later `audit` / `demo` / `export`).
The root `setup.sh` panel is for a git checkout on macOS only — not a daemon and
not a SaaS control plane.

## Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) (never use bare `pip install` / a hand-rolled venv
  for this repo)
- macOS for `./setup.sh` (Linux port is deferred)

## Bootstrap

```bash
uv sync
make verify
```

Or run `./setup.sh` and choose the sync / verify options. `make verify` must be
green before you open a PR.

## Licence headers

This project is Apache-2.0. Copyright attribution in `LICENSE` / `NOTICE` is
**hbauzan** — keep that notice when redistributing; do not replace it with a
generic “contributors” string.

**Policy for source files** (Python and shell under `vhecfsck/`, `tests/`,
`scripts/`, and root executables such as `setup.sh`):

1. New files **must** carry an Apache-2.0 header (SPDX short form or the full
   Apache appendix boilerplate).
2. Prefer the short form at the top of the file:

   ```text
   # Copyright 2026 hbauzan
   # SPDX-License-Identifier: Apache-2.0
   ```

   Use the comment syntax of the language (`#`, `//`, etc.).
3. Existing files without a header should gain one when substantially edited.
4. Do not invent a second copyright owner line in headers unless the owner has
   agreed in writing; contributions are licensed under Apache-2.0 to the project
   as stated in `LICENSE`.

Markdown docs, roadmap prose, and generated files do not require licence headers.

## Pull requests

- One logical change per PR; conventional commit messages
  (`feat|fix|test|docs|refactor|perf|build|ci|chore`).
- Never weaken a test to make it pass.
- Never add a dependency without recording the decision (ADR or ticket note).
- Never introduce a write path against an audited target — see [SECURITY.md](SECURITY.md).
- Use the PR template; link the roadmap ticket when there is one.

## Issues

Use the issue templates:

- **Bug** — paste the report JSON when you have one (safe after credential redaction).
- **False positive** — threshold / verdict disagreement.
- **Feature** — behaviour that is not an adapter.
- **New adapter** — engine support request.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
