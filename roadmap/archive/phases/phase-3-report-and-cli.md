# P3 — Report and CLI (retention branch)

**Goal:** make the audit engine consumable by a machine and by a human.

This is the half of the vertical slice that makes the tool *stay* installed: a CLI with a
contract a pipeline can depend on, and metrics a dashboard can graph. Everything here is
rendering and plumbing — no metric logic crosses into this phase.

**Entry criteria:** P2 exit checklist complete.

**Exit gate**

```bash
vhecfsck demo --scenario healthy    ; test $? -eq 0
vhecfsck demo --scenario drifted    ; test $? -eq 1
vhecfsck demo --scenario tombstoned ; test $? -eq 2
vhecfsck demo --scenario tiny       ; test $? -eq 3
vhecfsck audit --nonexistent-flag   ; test $? -eq 4
promtool check metrics < <(vhecfsck demo --scenario drifted --format prometheus)
```

---

## P3-01 — Report schema

**Depends on:** P2-01 · **Size:** M · **Touches:** `vhecfsck/models/report.py`, `tests/unit/test_report_model.py`

**Contract**
- `Report` (Pydantic v2, strict) matching [`01-architecture.md §6`](../../01-architecture.md):
  `schema_version`, `tool_version`, `verdict`, `run`, `target`, `counts`, `metrics`,
  `warnings`, `config` (the fully resolved effective config).
- `RunContext`: `started_at`, `duration_seconds`, `seed`, `deterministic`, host facts
  (CPU count, BLAS identification, platform), per-stage timings.
- `schema_version` is a module constant with a comment stating the change policy
  ([ADR-0008](../../adr/0008-report-schema-versioning.md)): additive → minor bump; removal or
  semantic change → major bump plus a migration note in `CHANGELOG.md`.
- `Report.compare(other)` returning a structured diff, for baseline mode in P8. Designed in
  now so the schema does not have to change later to accommodate it.
- No field may contain a credential, a raw vector, or document text. A test asserts this by
  auditing a corpus seeded with a recognisable secret string and grepping the serialised
  report.

**Tests first**
- Round-trip: `Report → JSON → Report` is lossless and idempotent.
- `extra = "forbid"` — an unknown field raises rather than being silently dropped.
- The secret-leak test above.
- `schema_version` matches the version recorded in the golden files.

---

## P3-02 — JSON renderer and published schema

**Depends on:** P3-01 · **Size:** M · **Touches:** `vhecfsck/report/json_report.py`, `schema/report-1.0.json`, `tests/e2e/test_json_golden.py`, `tests/fixtures/golden/`

**Contract**
- Deterministic serialisation: sorted keys, fixed float formatting (floats rounded to a
  documented precision at the serialisation boundary so that platform-level last-digit
  differences cannot break the byte-identity guarantee), `\n` line endings, trailing newline.
- Emit a JSON Schema to `schema/report-1.0.json`, generated from the Pydantic model in CI
  and committed. A drift check fails the build if the model and the committed schema diverge,
  which is what makes the schema a real contract rather than stale documentation.
- Golden files for every P1-08 scenario, with volatile fields normalised by a shared helper
  (never by hand-editing a golden file).

**Tests first**
- Golden comparison per scenario; a deliberate metric change produces a readable diff.
- The emitted JSON validates against the committed schema.
- Byte-identical output across two runs and across platforms (asserted in the CI matrix,
  where the macOS job is the one that actually catches float-formatting drift).

**Acceptance criteria**
- [ ] `jq` can consume the output; no `NaN`, `Infinity`, or non-finite literals are ever
      emitted (they are not valid JSON, and `jq` will reject the whole document).
- [ ] Updating a golden file requires an explicit `--update-golden` run, and the diff appears
      in the pull request.

---

## P3-03 — Terminal renderer

**Depends on:** P3-01 · **Size:** M · **Touches:** `vhecfsck/report/text_report.py`, `tests/e2e/test_text_output.py`

**Goal:** the output a human reads at 2 a.m. It must lead with the verdict and the reason,
not with a table of numbers.

**Contract**
- Structure: verdict banner → one-line summary of *why* → per-metric table (metric, value,
  threshold, state, evidence) → the offending detail for any failing metric (e.g.
  "412 of 2000 returned ids were dead") → remediation hints → warnings.
- Each failing metric prints a one-sentence explanation of the mechanism, in plain language,
  because the audience for a hubness failure has usually never heard the word "hubness". The
  explanation strings live in one module so they can be reviewed as copy rather than being
  scattered as f-strings.
- Rich for colour and tables when stdout is a TTY; on a non-TTY, plain ASCII with no escape
  codes at all. `NO_COLOR` and `TERM=dumb` are honoured.
- All human output goes to **stderr** when `--format json` is active, so stdout stays a pure
  machine channel.
- `UNAVAILABLE` renders visually distinct from `OK` — different glyph, different colour,
  and the reason inline. Confusing "unknown" with "fine" in the terminal would defeat the
  point of having the state at all.

**Tests first**
- Snapshot tests for each scenario with colour disabled.
- No ANSI codes when not a TTY.
- An `UNAVAILABLE` metric never renders in the same style as `OK` (asserted on the raw
  string).
- Width degradation at 80 columns and at 40 columns without wrapping into unreadability.

---

## P3-04 — `vhecfsck audit`

**Depends on:** P3-02, P3-03, P2-10 · **Size:** M · **Touches:** `vhecfsck/cli.py`, `tests/e2e/test_cli_audit.py`

**Contract**
- `vhecfsck audit --target <uri> [options]`, the primary command.
- Options: `--format text|json|prometheus`, `--output PATH`, `--queries PATH`, `--k`,
  `--queries-count`, `--hubness-sample`, `--k-hub`, `--hubness-source`, `--seed`,
  `--nprobe`, `--ef-search`, `--max-seconds`, `--max-memory-mb`, `--strict-unavailable`,
  `--only metric[,metric]`, `--skip metric[,metric]`, `--config PATH`, `-v/-vv/--quiet`,
  `--debug`, `--no-progress`.
- Exit codes exactly per [`02-metrics-spec.md §6`](../../02-metrics-spec.md). Typer's default
  exception handling is overridden; every path returns through the P0-05 mapper.
- Progress rendered to stderr, automatically suppressed on a non-TTY or with `--no-progress`.
  A CI log full of progress bar redraws is a real annoyance and a real reason people add
  `2>/dev/null`, which then hides the errors too.
- `--help` is genuinely useful: each option states its default and its unit.

**Tests first**
- Exit code per scenario, driven by the P1-08 expectations table.
- `--only canary_recall` marks the others `DISABLED` and they are excluded from the verdict.
- `--skip` and `--only` together → `UsageError` (exit `4`), not a silent precedence rule.
- An unreadable or nonexistent target → exit `4` with a message naming the problem, not a
  traceback.
- `--debug` shows the traceback; without it, only a one-line message plus a hint.
- No output on stdout other than the report when `--format json`.

---

## P3-05 — `vhecfsck demo`

**Depends on:** P3-04, P1-08 · **Size:** S · **Touches:** `vhecfsck/cli.py`, `tests/e2e/test_cli_demo.py`

**Goal:** the 60-second first impression, and the reason `uvx vhecfsck demo` is the hero
command in the README.

**Contract**
- `vhecfsck demo [--scenario NAME] [--size small|large] [--serve]`, running entirely on the
  synthetic adapter: no database, no credentials, no dataset, no network.
- Default scenario `tombstoned`, because the point of the demo is to *show a failure* — a
  demo that prints `OK` demonstrates nothing.
- Prints a short preamble naming the real-world issue being reproduced (with its upstream
  URL), then the normal audit output.
- `--serve` hands off to the P4 server so the same run can be inspected in 3D.
- Exit code follows the scenario's verdict like any other audit, so `demo` doubles as the
  smoke test for the exit-code contract.
- The contributor `setup.sh` Forty-two action becomes live when this command exists. Do
  not edit `setup.sh` unless the probe (`vhecfsck demo --help`) breaks.

**Tests first**
- Runs with only the base install — asserted by an environment that has no engine SDK
  installed at all, which is the property most likely to regress silently.
- Completes in under 20 s at `--size small`.
- Every scenario name is reachable and its exit code matches the table.

---

## P3-06 — Prometheus exporter

**Depends on:** P3-01 · **Size:** M · **Touches:** `vhecfsck/report/prometheus.py`, `tests/e2e/test_prometheus.py`

**Contract**
- Textfile-collector format (for `node_exporter`), also reused by the P4 `/metrics` endpoint.
- Series, all prefixed `vhecfsck_`:
  - `vhecfsck_canary_recall`, `vhecfsck_dfi_ratio`, `vhecfsck_hub_share_top1pct`,
    `vhecfsck_antihub_fraction`, `vhecfsck_partition_size_cv` — gauges.
  - `vhecfsck_metric_state{metric="…"}` — `0` OK, `1` WARN, `2` FAIL.
  - `vhecfsck_metric_unavailable{metric="…"}` — `1` when unavailable. **The value gauge is
    omitted entirely** in that case, so a dashboard shows a gap rather than a plausible
    number, and an alert on staleness fires.
  - `vhecfsck_audit_verdict`, `vhecfsck_audit_duration_seconds`,
    `vhecfsck_audit_timestamp_seconds`, `vhecfsck_up`.
  - Counts: `vhecfsck_vectors_live`, `vhecfsck_vectors_deleted`.
- Labels: `engine`, `index`, `metric_space`, `target` (redacted, low cardinality). No label
  may ever carry a vector ID, a query, or a credential — an unbounded label is how a
  monitoring exporter takes down a Prometheus server.
- Every series has `# HELP` and `# TYPE`.

**Tests first**
- `promtool check metrics` passes on every scenario's output (subprocess test, skipped with a
  clear message when `promtool` is absent locally, required in CI).
- An unavailable metric emits no value gauge and does emit the unavailable flag.
- Label cardinality is bounded: no label value derives from per-vector data.

---

## P3-07 — `vhecfsck export`

**Depends on:** P3-02 · **Size:** S · **Touches:** `vhecfsck/cli.py`, `tests/e2e/test_cli_export.py`

**Contract**
- `vhecfsck export --report report.json --format prometheus|text|markdown` — re-render a
  stored report without re-running the audit. Cheap to build, and it is what makes a
  6-minute audit result usable in three places without paying for it three times.
- `markdown` targets pull-request comments and GitHub Actions job summaries.
- Reports from a newer major `schema_version` are refused with a clear message; older minor
  versions are accepted.

**Tests first**
- Every format renders from a golden report.
- A future major schema version → exit `4` with an actionable message.

---

## P3-08 — Exit-code contract test suite

**Depends on:** P3-04, P3-05 · **Size:** S · **Touches:** `tests/e2e/test_exit_codes.py`

**Goal:** the exit-code contract is the tool's public API for every CI user. It gets its own
dedicated suite so that a change to it can never be an accident.

**Contract**
- A table-driven suite invoking the real CLI as a subprocess (not the Typer test runner) for
  every documented code: `0`, `1`, `2`, `3`, `4`, `70`.
- `70` is provoked by a fault-injection flag available only under a test environment
  variable.
- Also asserts: no interactive prompt is ever reachable, and `--quiet` still returns the
  correct code with empty stdout.

**Acceptance criteria**
- [ ] Every code in [`02-metrics-spec.md §6`](../../02-metrics-spec.md) is exercised.
- [ ] The suite is referenced from `SECURITY.md`/`CONTRIBUTING.md` as a stability contract.

---

## Phase exit checklist

- [ ] Every exit-gate command above behaves exactly as written.
- [ ] `uvx vhecfsck demo` works with the base install only, no engine SDK present.
- [ ] Golden reports committed for all scenarios; JSON validates against the published
      schema; schema-drift check active in CI.
- [ ] `promtool check metrics` green for every scenario.
- [ ] Terminal output leads with the verdict and the reason, and renders `UNAVAILABLE`
      distinctly from `OK`.
- [ ] No metric logic exists in `report/` or `cli.py` (import-linter enforced).
