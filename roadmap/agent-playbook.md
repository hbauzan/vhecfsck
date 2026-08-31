# Agent Playbook

**Read this before executing any ticket.** It defines the workflow, the guardrails, and the
definition of done that applies to every ticket without exception.

This roadmap is written to be executed by AI coding agents. The tickets are sized so that one
ticket is one session, ending with a green verification gate and a single commit. The guardrails
exist because the most common way an agent damages a codebase is not by writing bad code — it is
by silently widening its own scope, weakening a test that was inconveniently failing, or guessing
at an ambiguous requirement instead of stopping to ask.

---

## 1. The execution loop

**Step 1 — Orient.** Read, in this order:
1. The ticket in its phase file. Read the whole ticket, including Guardrails.
2. Every ADR it cites.
3. The section of [`02-metrics-spec.md`](02-metrics-spec.md) it implements, if it touches
   `core/`.
4. The layering rules in [`01-architecture.md §4`](01-architecture.md).

**Step 2 — Confirm the ticket is executable.** Verify its dependencies are complete, that the
acceptance criteria are unambiguous, and that the scope fits one session. If any of those fails,
**stop and report** rather than proceeding on an interpretation. An hour of clarification is
cheaper than a day of work in the wrong direction.

**Step 3 — Write the tests first.** Every ticket lists a "Tests first" section. Write those tests,
run them, and **watch them fail for the right reason**. A test that passes before the
implementation exists is testing nothing, and this is the single most common way an agent produces
work that looks complete and verifies nothing.

**Step 4 — Implement the minimum that satisfies the tests and the contract.** No speculative
generality. No adjacent refactoring. No "while I was in here".

**Step 5 — Verify at the right moment.** Three gears; do not collapse them.

- **While coding:** run the test you just wrote (TDD). If the change crosses a neighbour
  seam, run that file too. `make test` is the uninstrumented default suite — inner loop,
  not the gate.
- **Ticket ready to merge:** `make verify` **once**. It must be green. Not "green except
  for a pre-existing failure" — green. If something unrelated is broken, that is a finding
  to report, not a reason to proceed. Do not run it on every pull of `main`.
- **Version tag:** `make verify-full`. Always.

`make verify` runs the default suite **once**, instrumented (`coverage`). `make test` is
not a prerequisite of the gate.

**Step 6 — Check the acceptance criteria one by one.** Actually check them. Do not assume that
passing tests implies the criteria are met; they frequently include properties the tests do not
cover, such as timing budgets or memory ceilings.

**Step 7 — Update the paperwork.** `CHANGELOG.md` under `[Unreleased]`. The ticket's status in
[`backlog.md`](backlog.md). Any doc the ticket names.

**Step 8 — Deliver one commit.** Local commits while working are free. On delivery,
squash to one conventional commit, then merge to `main` after explicit OK.
```text
<type>(<scope>): <summary>

<why, not what>

Ticket: P2-04
```
Types: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`.

**Step 9 — Report.** State what was built, what was verified, any deviation from the ticket and
why, and anything discovered that should become a new ticket.

---

## 2. Hard guardrails

These are not style preferences. Violating one means the work is wrong regardless of whether the
tests pass.

1. **Never weaken a test to make it pass.** Not by loosening a tolerance, not by adding a skip,
   not by deleting an assertion, not by `xfail`. If a test is genuinely wrong, that is a finding
   to report with evidence — it is never a step to take unilaterally, because the test may be the
   only thing encoding a correction from the metrics spec.

2. **Never write to an audited target.** No exceptions, in any code path, including tests.
   Fixtures that must create a pathology live in the test harness, architecturally separated from
   the package. See [ADR-0001](adr/0001-read-only-by-default.md).

3. **Never report a number you could not compute.** `UNAVAILABLE` with a reason, always. A
   plausible-looking substitute is the most damaging bug this project can ship. See
   [ADR-0013](adr/0013-adapter-protocol.md).

4. **Never add a dependency without an ADR.** Including a transitive one pulled in for
   convenience, and including a front-end package.

5. **Never exceed the ticket's declared scope.** If you find a bug outside it, report it as a new
   ticket. A single-purpose commit is reviewable; a commit that also fixed three other things is
   not.

6. **Never leave `make verify` red.** Not "I'll fix it in the next ticket".

7. **Never guess at an ambiguous specification.** Stop and ask. Especially for anything numeric:
   a threshold, a tolerance, a default. A guessed constant becomes load-bearing within two
   tickets and nobody remembers it was a guess.

8. **Never bypass a guard.** No `# type: ignore` without a reason comment, no `# noqa` without a
   reason, no `--no-verify`, no adding a file to an exclusion list. Guards that can be bypassed
   silently are decoration.

9. **Never put metric logic outside `core/`.** Not in an adapter, not in a renderer, not in the
   front end. See [`01-architecture.md §4`](01-architecture.md).

10. **Never use the global RNG or rely on unordered iteration** in anything that reaches output.
    Determinism is an invariant, not an aspiration.

11. **Never write a number into documentation that nobody measured.** No estimated benchmarks, no
    rounded-up performance claims. If it is not measured, say it is not measured.

12. **Never code against a remembered API.** Engine SDKs change between releases. Inspect the
    pinned version and record what is actually available. A confident call to a method that no
    longer exists is a wasted session; a confident call to a method whose *semantics* changed is
    worse, because it will pass tests and be wrong.

---

## 3. Definition of done

A ticket is done when **all** of these hold. No partial credit.

- [ ] Every test listed in "Tests first" exists, and each one failed before the implementation
      and passes after.
- [ ] Every acceptance criterion individually checked.
- [ ] `make verify` green.
- [ ] Coverage gates met (≥90% `core/`, ≥80% overall).
- [ ] `mypy --strict` clean on the typed packages.
- [ ] No new lint suppressions, type ignores, or skipped tests. If one is unavoidable, it carries
      a reason comment and is called out in the report.
- [ ] Layering contracts satisfied.
- [ ] Read-only guard clean.
- [ ] Docstrings on new public functions in `core/` and `models/`, citing the spec section where
      applicable.
- [ ] `CHANGELOG.md` updated.
- [ ] Ticket status updated in [`backlog.md`](backlog.md).
- [ ] Exactly one commit, conventional message, referencing the ticket.
- [ ] Report written: what was built, what was verified, deviations, discoveries.

---

## 4. When to stop and ask

Stopping is a successful outcome in every one of these cases. Proceeding is the failure.

- The ticket's acceptance criteria are ambiguous or contradictory.
- The metrics spec does not cover a case you have hit.
- An ADR appears to be wrong, or two ADRs conflict.
- A dependency you need is not listed in the ticket.
- The implementation requires a numeric constant the spec does not provide.
- The work does not fit one session.
- An engine's actual API differs from what the ticket assumed.
- A pre-existing failure blocks verification.
- You are about to do any of the things in §2.

Report format: what you were doing, what you found, the options as you see them, and which one
you would choose and why. Then wait.

---

## 5. Anti-patterns specific to this project

Each of these has already happened somewhere, in some project, and each is easy to do here.

| Anti-pattern | Why it is wrong here |
| :--- | :--- |
| Returning `0.0` when a count is unknown | Reports a perfectly healthy index precisely when the tool knows nothing. [ADR-0004](adr/0004-metric-result-states-and-exit-codes.md) exists for this. |
| Using the engine's reported distances for recall | Under quantisation those are approximations of the thing being audited. Recompute from vectors. |
| Optimising the naive oracle in `tests/oracle/` | Its only value is being independently, obviously correct. If it is too slow, shrink the input. |
| Simulating degradation with random noise | Would let us claim detection of a mechanism we never simulated. [ADR-0014](adr/0014-synthetic-adapter-first.md). |
| Uniform random decimation of the 3D scene | Randomly discards the hubs, which are the finding. [ADR-0009](adr/0009-scene-transport-and-lod.md). |
| Sharing k-means between the synthetic adapter and the partition metric | Makes the test circular: the instrument would be measuring itself. |
| Tuning a threshold until the warnings stop | Some corpora are genuinely pathological. [ADR-0011](adr/0011-thresholds-and-baseline-mode.md). |
| Adding a field to the report without bumping the schema and updating goldens | The report is a public contract. [ADR-0008](adr/0008-report-schema-versioning.md). |
| `float16` anywhere in an accumulation | Reorders near-ties and corrupts the oracle. [ADR-0005](adr/0005-ground-truth-precision-and-blocking.md). |
| Forgetting to clamp negative squared distances before `sqrt` | Produces `nan` and silently poisons a whole row of ground truth. |
| Skipping a test because a capability is absent | Test the `UNAVAILABLE` path instead. A skipped test hides a regression. |

---

## 6. Useful commands

```bash
./setup.sh help          # contributor console (macOS); ./setup.sh verify when the gate exists
make verify              # merge gate — once per ticket (suite via coverage)
make verify-full         # version / nightly: slow, integration, perf, mutation
make fmt                 # auto-fix formatting and lint
make test                # inner-loop default suite, no coverage
make test-fast           # same as test, quieter
make web-build           # build the front-end bundle
make demo                # run the demo scenario locally
make demo-gif            # regenerate the README asset (P6-07)

pytest tests/oracle -q                    # differential tests against naive references
pytest tests/contract -q                  # adapter conformance
pytest -m "not slow and not integration"  # the default fast set
pytest --collect-only -q                  # what exists without running it
```
