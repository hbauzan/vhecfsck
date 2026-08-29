# P0 — Foundation and Guardrails

**Goal:** make it structurally difficult to write bad code, before any code exists.

Every quality property this project claims — read-only safety, determinism, strict typing,
layering — is either enforced mechanically from the first commit or is a lie by the tenth.
This phase builds the enforcement, not the product.

**Entry criteria:** empty repository containing only `roadmap/`.

**Exit gate**

```bash
make verify && vhecfsck --version && python -c "import vhecfsck; print(vhecfsck.__version__)"
```

`make verify` must run ruff, ruff format `--check`, `mypy --strict` on the typed packages,
pytest with coverage gates, and the import-layering contracts — and be green.

---

## P0-01 — Bootstrap package and packaging

**Depends on:** — · **Size:** M · **Touches:** `pyproject.toml`, `vhecfsck/__init__.py`, `vhecfsck/__main__.py`, `.gitignore`, `.python-version`

**Goal:** an installable, importable, versioned package.

**Contract**
- `git init`, `main` as the default branch, `.gitignore` for Python + Node + macOS.
- `pyproject.toml` with `hatchling` backend, `requires-python = ">=3.11"`, project name
  `vhecfsck`, Apache-2.0, and `[project.scripts] vhecfsck = "vhecfsck.cli:main"`.
- Version single-sourced in `pyproject.toml`; `vhecfsck.__version__` reads it via
  `importlib.metadata.version`. No duplicated version strings anywhere.
- Optional extras declared, even though empty for now: `lancedb`, `qdrant`, `postgres`,
  `server`, `dev`, `all`. Base dependencies are `numpy` and `typer` only — nothing else
  belongs in the base install ([ADR-0002](../adr/0002-packaging-and-toolchain.md)).
- `__init__.py` exposes `__version__` and nothing else. No imports of submodules, no side
  effects: `import vhecfsck` must stay fast enough that CLI startup is not noticeable.

**Tests first**
- `tests/unit/test_package.py`: `__version__` is a valid PEP 440 string and matches
  `importlib.metadata.version("vhecfsck")`.
- Importing `vhecfsck` does not import `numpy` (assert via `sys.modules`) — proves the
  lazy-import discipline holds.

**Acceptance criteria**
- [ ] `uv sync` succeeds on a clean checkout.
- [ ] `uv run python -c "import vhecfsck"` succeeds in under 150 ms.
- [ ] `uv build` produces a valid wheel and sdist.

**Guardrails:** do not add dependencies beyond `numpy` and `typer`. Every later dependency
arrives through the ticket that needs it, so the base install stays lean and `uvx vhecfsck
demo` stays fast.

---

## P0-02 — Lint, format and strict typing configuration

**Depends on:** P0-01 · **Size:** S · **Touches:** `pyproject.toml`

**Contract**
- Ruff as the only linter and formatter. Enable at minimum `E,F,W,I,N,UP,B,A,C4,SIM,ARG,PTH,RUF`,
  plus `ANN` (annotations) and `D` (docstrings) for `vhecfsck/core/` and `vhecfsck/models/`.
- `mypy` in strict mode for `vhecfsck/core`, `vhecfsck/models`, `vhecfsck/adapters`. The rest
  of the package is checked non-strictly; tests are checked leniently.
- `disallow_any_generics`, `warn_return_any`, `no_implicit_optional`, and
  `warn_unused_ignores` on. NumPy typing via `numpy.typing.NDArray` with explicit dtypes —
  `np.ndarray` bare is a lint failure in `core/`, because a silent `float64` promotion in a
  1M × 768 matmul doubles memory and nobody notices until the OOM.

**Acceptance criteria**
- [ ] `ruff check .` and `ruff format --check .` are clean.
- [ ] `mypy` reports zero errors.
- [ ] A deliberately untyped function added to `core/` fails the check (verify once, then
      revert).

---

## P0-03 — Test harness and coverage gates

**Depends on:** P0-01 · **Size:** S · **Touches:** `pyproject.toml`, `tests/conftest.py`, `tests/unit/`

**Contract**
- pytest with `--strict-markers`, `--strict-config`, and `-ra`.
- Registered markers: `slow`, `integration`, `perf`, `requires_docker`, `requires_lancedb`,
  `requires_qdrant`, `requires_postgres`. Default run excludes `slow`, `integration`, `perf`.
- Coverage via `pytest-cov`, `fail_under = 80` overall plus a separate `core/`-scoped
  invocation at `fail_under = 90` ([`testing-strategy.md`](../testing-strategy.md)).
- Directory skeleton per [`01-architecture.md §2`](../01-architecture.md): `unit`, `property`,
  `oracle`, `contract`, `integration`, `e2e`, `perf`, `fixtures`.
- `conftest.py` provides a seeded `rng` fixture and a `deterministic_env` autouse fixture
  that pins `PYTHONHASHSEED` and single-threaded BLAS (`OMP_NUM_THREADS=1`) for reproducible
  numerics in tests. Multi-threaded BLAS reduction order is not deterministic, and that will
  eventually produce a flaky test that costs a day to diagnose.

**Acceptance criteria**
- [ ] `pytest -q` passes with the placeholder tests.
- [ ] `pytest --collect-only -m slow` collects nothing yet but the marker is valid.
- [ ] An unregistered marker fails collection.

---

## P0-04 — `make verify` as the single quality gate

**Depends on:** P0-02, P0-03 · **Size:** S · **Touches:** `Makefile`

**Contract**
- `make verify` = `lint` + `format-check` + `typecheck` + `test` + `coverage` + `layers`.
  This is the one command every ticket must leave green, and the one command CI runs.
- `make verify-full` additionally runs `slow`, `integration`, `perf` and mutation testing
  (targets may be stubs that exit zero until the owning phase lands them).
- Also: `make fmt`, `make test-fast`, `make clean`, `make web-build`, `make demo`.
- Every target is idempotent and needs no arguments. An agent must never have to assemble a
  verification command from memory — ambiguity there is how unverified commits happen.

**Acceptance criteria**
- [ ] `make verify` exits `0` on a clean tree and non-zero when any sub-step fails.
- [ ] `make verify` completes in under 60 s at this phase.

---

## P0-05 — Error taxonomy and exit-code contract

**Depends on:** P0-01 · **Size:** M · **Touches:** `vhecfsck/errors.py`, `tests/unit/test_errors.py`

**Goal:** implement [ADR-0004](../adr/0004-metric-result-states-and-exit-codes.md) once,
centrally, before anything can raise an ad-hoc exception.

**Contract**
- `VhecfsckError` base, with `exit_code`, a stable machine-readable `code` string, and a
  human `hint`.
- Subclasses: `UsageError` (4), `TargetConnectionError` (4), `CapabilityError` (3),
  `InconclusiveError` (3), `InternalError` (70).
- `ExitCode` `IntEnum`: `OK=0, WARN=1, FAIL=2, INCONCLUSIVE=3, USAGE=4, INTERNAL=70`.
- A single top-level handler maps any uncaught exception to `70` with a short message and a
  pointer to `--debug` for the traceback. Users never see a raw traceback by default; agents
  and bug reporters always can.

**Tests first**
- Every subclass maps to its documented code; the mapping is asserted from a table so a new
  error type without a code fails the test.
- `code` strings are unique and stable (asserted against a frozen list).

**Acceptance criteria**
- [ ] `ExitCode` values match [`02-metrics-spec.md §6`](../02-metrics-spec.md) exactly.
- [ ] No bare `raise Exception` or `SystemExit` anywhere outside `errors.py` (ruff rule).

---

## P0-06 — Structured logging with credential redaction

**Depends on:** P0-05 · **Size:** M · **Touches:** `vhecfsck/logging.py`, `tests/unit/test_logging_redaction.py`

**Goal:** make leaking a connection string structurally hard. This tool runs next to
production databases and its output gets pasted into issue trackers.

**Contract**
- `stdlib logging` configured with a plain human formatter and an opt-in JSON formatter
  (`--log-format json`).
- A `RedactionFilter` applied to every handler, rewriting: `postgres://user:pass@host`,
  `?api_key=`, `Authorization:` headers, anything matching common token shapes, and any
  value of an env var whose name matches `(PASSWORD|SECRET|TOKEN|API_KEY)`.
- Redaction applies to log records **and** to `TargetDescriptor.location`, so a report is
  safe to attach to a GitHub issue.
- Verbosity: `-v` / `-vv` / `--quiet`; all diagnostics to stderr so stdout stays a clean
  machine-readable channel for `--format json`.

**Tests first**
- Parametrised table of ~12 secret-bearing strings; assert none survives into the emitted
  record.
- A password containing regex metacharacters is still redacted.
- Redaction never truncates a non-secret URL into uselessness (`file:///data/x.lance`
  survives intact).

**Acceptance criteria**
- [ ] Redaction is applied by default; there is no flag to turn it off.
- [ ] `--format json` writes only the report to stdout, nothing else.

---

## P0-07 — Configuration and default threshold profile

**Depends on:** P0-01 · **Size:** M · **Touches:** `vhecfsck/config.py`, `tests/unit/test_config.py`

**Contract**
- `AuditConfig` dataclass (frozen): seed, `queries`, `k`, `hubness_sample_size`, `k_hub`,
  `hubness_source`, `max_seconds`, `max_memory_mb`, `block_working_set_mb`,
  `strict_unavailable`, per-metric enable flags, and a `Thresholds` mapping.
- Default thresholds exactly as in [`02-metrics-spec.md`](../02-metrics-spec.md). Defaults
  live in code with a comment pointing at the spec section, and a test asserts the code
  matches the documented table so the two cannot drift.
- Precedence, lowest to highest: built-in defaults → config file
  (`vhecfsck.toml` / `[tool.vhecfsck]` in `pyproject.toml`) → `VHECFSCK_*` env vars → CLI flags.
- Unknown config keys are a `UsageError`, never ignored. A silently ignored typo in a
  threshold is a silently disabled safety check.

**Tests first**
- Precedence is verified at every level with a single overridden key.
- Defaults match the spec table (table-driven).
- An unknown key raises `UsageError`; an out-of-range threshold (warn stricter than fail
  for the direction) raises `UsageError`.

**Acceptance criteria**
- [ ] `AuditConfig` is immutable and fully typed.
- [ ] The effective, fully-resolved config is serialisable for embedding in the report.

---

## P0-08 — Import-layering enforcement

**Depends on:** P0-04 · **Size:** S · **Touches:** `pyproject.toml`, `.importlinter`, `Makefile`

**Contract**
- `import-linter` contracts encoding [`01-architecture.md §4`](../01-architecture.md)
  verbatim: `models` imports nothing internal; `core` never imports `adapters`, `server`,
  `cli`, `report`; `adapters` never imports `core`; `report` never imports `core` or
  `adapters`.
- Wired into `make verify` as the `layers` target.

**Acceptance criteria**
- [ ] `lint-imports` passes.
- [ ] Adding `from vhecfsck.adapters import base` to a `core/` module fails the gate
      (verify once, then revert).

---

## P0-09 — Read-only static guard

**Depends on:** P0-04 · **Size:** M · **Touches:** `scripts/check_readonly.py`, `Makefile`, `tests/unit/test_readonly_guard.py`

**Goal:** the first and cheapest layer of defence for the project's most important
invariant ([ADR-0001](../adr/0001-read-only-by-default.md)).

**Contract**
- A script that walks `vhecfsck/adapters/**` and `vhecfsck/core/**` with `ast` — not regex,
  because regex on source produces both false positives in strings and false negatives on
  aliased calls — and fails on any call whose attribute name is in a denylist:
  `delete, delete_by_filter, upsert, insert, add, merge_insert, update, drop, create_index,
  optimize, compact, cleanup_old_versions, restore, commit, execute` (SQL `execute` is
  allowed only through a vetted read-only helper), plus any string literal matching
  `VACUUM|REINDEX|DROP |DELETE |UPDATE |INSERT |TRUNCATE|ALTER `.
- Allowlist by explicit `# readonly-ok: <reason>` comment, which requires a reason and is
  reported in the script's summary output so exemptions stay visible rather than
  accumulating quietly.
- Wired into `make verify` and CI.

**Tests first**
- A fixture module containing `client.delete(...)` fails the check.
- A fixture with the same call inside a string literal or a comment does not fail.
- An aliased write (`f = tbl.delete; f()`) fails — this is the case regex would miss.
- An `# readonly-ok:` exemption passes and appears in the summary.

**Acceptance criteria**
- [ ] The check runs in under 2 s on the whole package.
- [ ] Zero exemptions exist at the end of this phase.

---

## P0-10 — Continuous integration

**Depends on:** P0-04 · **Size:** M · **Touches:** `.github/workflows/ci.yml`, `.github/workflows/nightly.yml`

**Contract**
- `ci.yml` on push and pull request: `ubuntu-latest` × Python 3.11/3.12/3.13, plus one
  `macos-latest` × 3.12 job (this project's primary dev machine is macOS/arm64, and BLAS
  behaviour differs enough there to matter). `uv` for install with a cached environment.
- Steps: `make verify`, then upload coverage. Concurrency group cancels superseded runs.
- Python 3.14 runs as an advisory `continue-on-error` job so ecosystem readiness is visible
  without blocking merges.
- `nightly.yml` on a schedule: `make verify-full`, plus a job that installs the newest
  release of each engine SDK to catch upstream drift early
  ([risk R4](../risk-register.md)).
- All workflow permissions default to `contents: read`.

**Acceptance criteria**
- [ ] CI is green on `main`.
- [ ] Total wall time under 8 minutes at this phase.
- [ ] A failing lint rule fails the build.

---

## P0-11 — Community, security and licence files

**Depends on:** P0-01 · **Size:** S · **Touches:** `LICENSE`, `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`

**Contract**
- Apache-2.0 (patent grant matters for infrastructure tooling that vendors may adopt).
- `README.md` as a placeholder with the real quickstart shape and a `TODO(P9-01)` marker for
  the GIF, so the hero asset has a reserved slot rather than being bolted on at release.
- `SECURITY.md` states the read-only invariant explicitly and defines a private reporting
  channel — a hypothetical write path is a security issue, not a bug.
- Issue templates: bug report (with a "paste your report JSON" field, safe because of
  P0-06), false-positive report (thresholds are the likeliest complaint), feature request,
  new-adapter request.
- `CHANGELOG.md` seeded with `## [Unreleased]`.

**Acceptance criteria**
- [ ] `README.md` contains no claim that is not yet true (no fabricated benchmarks).
- [ ] Licence headers policy documented in `CONTRIBUTING.md`.

---

## P0-12 — Agent operating rules at the repository root

**Depends on:** P0-11 · **Size:** S · **Touches:** `AGENTS.md`

**Contract**
- Distil [`agent-playbook.md`](../agent-playbook.md) into a root `AGENTS.md` that any coding
  agent will read automatically: the verify command, the commit convention, the hard
  guardrails, and the pointer into `roadmap/`.
- Must include, verbatim and prominently: never weaken a test to make it pass; never add a
  dependency without an ADR; never write to an audited target; never leave `make verify`
  red; stop and report rather than guess when a spec is ambiguous.
- Keep it under roughly 80 lines. `AGENTS.md` is read on every session, so length is a real
  cost; detail belongs in `roadmap/`.

**Acceptance criteria**
- [ ] `AGENTS.md` exists, is under 80 lines, and links to the playbook and the metrics spec.

---

## P0-13 — Reserve the project namespace

**Depends on:** P0-01 · **Size:** S · **Touches:** — (external, plus `pyproject.toml` metadata)

**Goal:** claim `vhecfsck` before someone else does, and before the launch depends on it.

**Contract**
- Verified at planning time: `vhecfsck` returns `404` from `pypi.org/pypi/vhecfsck/json`,
  i.e. the name is free. Re-verify, then claim it.
- Create the GitHub repository `vhecfsck`, public, and reserve the matching PyPI name by
  publishing a `0.0.0` placeholder via TestPyPI-validated Trusted Publishing
  ([`release-plan.md`](../release-plan.md)).
- Record the canonical spelling decision in [ADR-0012](../adr/0012-naming.md), including the
  open question about what the `H` stands for in public-facing copy — that needs an owner
  decision before the README is written, not after.
- Fill in `pyproject.toml` URLs: homepage, repository, issues, changelog.

**Acceptance criteria**
- [ ] `pip index versions vhecfsck` resolves to the reserved project.
- [ ] Only lowercase `vhecfsck` appears in code, package names and CLI output.

---

## P0-14 — Pre-commit hooks

**Depends on:** P0-04, P0-09 · **Size:** S · **Touches:** `.pre-commit-config.yaml`

**Contract**
- Hooks: ruff (fix), ruff-format, trailing whitespace, end-of-file, large-file guard,
  private-key detection, TOML/YAML/JSON validity, and the read-only guard from P0-09.
- Deliberately excluded: mypy and pytest. Slow hooks get bypassed with `--no-verify`, and a
  bypassed hook protects nothing. Those belong in `make verify` and CI.

**Acceptance criteria**
- [ ] `pre-commit run --all-files` passes.
- [ ] Setup instructions are in `CONTRIBUTING.md`.

---

## P0-15 — Contributor console (`setup.sh`)

**Depends on:** P0-01 · **Size:** M · **Touches:** `setup.sh`, `tests/e2e/test_setup_sh.py`

**Goal:** a Hitchhiker-themed contributor panel for a git checkout on macOS. This is not
the product. The product is `uvx vhecfsck`. The panel must not grow a daemon, a SaaS
publish path, or a second long-lived UI process.

**Contract**
- Root `setup.sh`, executable, `#!/usr/bin/env bash`, Bash 3.2-safe (stock macOS bash).
- Banner exactly: `DON'T PANIC — Vector Index`.
- Menu language: English. Visual hierarchy: the technical action is primary
  (bold white); the Hitchhiker quote is secondary (dim grey, in parentheses).
  Every visible option still carries these labels, unchanged:
  - `[1]` Infinite Improbability Drive → detect `uv`, then `uv sync` (never `--all-extras`).
  - `[2]` The mice would like a word → `make verify` when a Makefile exists.
  - `[3]` Forty-two → `uv run vhecfsck demo` when that command exists (P3-05).
  - `[4]` Heart of Gold → `uv run vhecfsck serve` when that command exists (P4-06),
    **foreground**. Ctrl+C stops the process. No pid files, no `nohup`, no port killing.
  - `[0]` So long, and thanks for all the fish → leave the panel.
  - Invalid input: `I think you ought to know I'm feeling very depressed.`
- Missing capabilities (`make verify`, `demo`, `serve`) are **inconclusive** (exit `3`),
  never faked as healthy. Copy may use *This must be Thursday. I never could get the hang
  of Thursdays.*
- macOS (`uname -s` = `Darwin`) only. Any other OS exits `3` and points at `P9-09`.
  Linux is not "best effort" here — it is absent until that ticket is executed after a
  real Linux test.
- `uv` missing: ask `[y/N]` and use the official installer only on a TTY. Non-interactive
  or `SETUP_SH_SKIP_PREREQ_PROMPT=1` prints the docs URL and exits `3`. No Node, no
  Homebrew auto-install.
- Non-interactive verbs (they add value for agents; start/stop/status do not — no daemon):
  `help`, `sync`, `verify`, `demo`, `serve`. Unknown verb → exit `4`.
- Exit codes follow the skill taxonomy: `0` OK, `2` FAIL (gate or sync failed), `3`
  INCONCLUSIVE, `4` USAGE.
- Forbidden in this script: Hugging Face / Spaces, Vite / `:5173`, background supervisors,
  log directories, raw `uvicorn`. Three.js, HUD, and `.npz` reuse stay in P4/P6.

**Tests first**
- `tests/e2e/test_setup_sh.py`: help copy (banner + labels, no SaaS/daemon/Vite), menu
  exit line, usage `4`, Linux `3`, `uv sync` without `--all-extras` (PATH-injected fake
  `uv`), `verify` inconclusive without Makefile and `2` when the gate fails, `demo` /
  `serve` inconclusive until those commands exist, source-level ban on daemon/SaaS
  mechanics. Each test failed before `setup.sh` existed.

**Acceptance criteria**
- [ ] `./setup.sh help` exits `0` and prints `DON'T PANIC — Vector Index`.
- [ ] `echo 0 | ./setup.sh` prints `So long, and thanks for all the fish` and exits `0`.
- [ ] `SETUP_SH_UNAME=Linux ./setup.sh help` exits `3`.
- [ ] Running help creates neither `.pids/` nor `logs/`.
- [ ] `uv run pytest tests/e2e/test_setup_sh.py` is green.

**Guardrails:** do not add Node, a second process model, or a Python dependency. Do not
implement Linux. Do not open a browser. Do not write an ADR — no new package is added.

---

## Phase exit checklist

- [ ] `make verify` green locally and in CI on three Python versions.
- [ ] `vhecfsck --version` prints the version and exits `0`.
- [ ] Layering, read-only guard and coverage gates all fail loudly when deliberately
      violated. **Test the guards by breaking them once each** — an untested guard is
      indistinguishable from a guard that does nothing, and this is the only phase where
      breaking things is free.
- [ ] `vhecfsck` reserved on GitHub and PyPI.
- [ ] `AGENTS.md` present at the root.
- [ ] `./setup.sh help` exits `0` and prints `DON'T PANIC — Vector Index`.
- [ ] Zero `# readonly-ok` exemptions and zero `# type: ignore` without a reason comment.
