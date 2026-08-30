# QUALITY GATE & HARD GUARDRAILS

The other modules describe *what to do*. This one describes **what fails the build when you
don't**.

Nothing here is a style preference. A rule that depends on an agent remembering it is not a
rule — it is a hope. Every item below is either enforced by a command or written where the
agent cannot miss it.

---

## 1. THE SINGLE GATE

Every repo exposes **one** command that decides whether work is acceptable:

<!-- agents-md:begin gate -->
```bash
make verify        # lint + format-check + typecheck + test + coverage + guards
```

- **Green or you are not finished.** Not "green except a pre-existing failure". If something
  unrelated is broken, that is a finding to report, not a licence to proceed.
- **Never bypass it.** No `--no-verify`, no running a subset and calling it verified.
<!-- agents-md:end gate -->

Two more properties that make it work:

- **Idempotent and argument-free.** An agent must never assemble a verification command from
  memory — ambiguity there is exactly how unverified work gets reported as done.
- **Fast enough to run every time.** Measure the default gate on the project's reference
  machine and record that number — do not invent a budget. Anything too slow for every commit
  goes in `make verify-full` (integration, perf, mutation) and runs in CI or on demand.
- Targets that do not apply yet are **stubs that exit `0`**, so the gate exists from the first
  commit instead of arriving once the codebase is already messy.

Base template: [`templates/Makefile`](./templates/Makefile) — copy to the workspace root.

---

## 2. HARD GUARDRAILS

Violating one of these means the work is wrong **regardless of whether the tests pass**.

<!-- agents-md:begin guardrails -->
1. **Never weaken a test to make it pass** — not a loosened tolerance, a skip, an `xfail`, or
   a deleted assertion. A test you believe is wrong is a finding to report with evidence.
2. **Never add a dependency without recording the decision.** Transitive ones pulled in for
   convenience count, and so do front-end packages.
3. **Never exceed the declared scope.** A bug found outside it becomes a new issue. A
   single-purpose commit is reviewable; one that also fixed three other things is not.
4. **Never leave the gate red.** "I'll fix it next commit" is how red becomes permanent.
5. **Never bypass a guard.** No `# type: ignore` or `# noqa` without a reason comment, no
   `--no-verify`, no adding a file to an exclusion list. A silently bypassable guard is
   decoration.
6. **Never code against a remembered API** — inspect the pinned version. Provider SDKs move
   fast, and a call to a method whose *semantics* changed is worse than one to a method that
   vanished: the second fails loudly, the first passes tests and is wrong.
7. **Never use the global RNG or rely on unordered iteration** in anything that reaches
   output. Determinism is an invariant, not an aspiration.
8. **Never write a number into documentation that nobody measured.** No estimated benchmarks,
   no rounded-up latency or token costs.
9. **Never guess at an ambiguous specification** — especially a numeric one. Stop and ask. A
   guessed constant becomes load-bearing within two tasks and nobody remembers it was a guess.
<!-- agents-md:end guardrails -->

These nine are the canonical list for the **generated** mode in §6. Edit them **here**, never
in a generated `AGENTS.md`. A product overlay or an opt-out `AGENTS.md` may add rules; it
must not silently drop these nine.

---

## 3. DEFINITION OF DONE

A task is done when **all** of these hold. There is no partial credit.

- [ ] Every planned test exists, and each one **failed before** the implementation and passes
      after. A test that passed before the code existed is testing nothing, and this is the
      most common way an agent produces work that looks complete and verifies nothing.
      **Escape:** if debugging Phase 5 documented that no correct seam exists, this item does
      not apply; the finding (architecture blocking the lock-down) **does**, and must be in
      the report.
- [ ] Every acceptance criterion checked individually. Passing tests do not imply the criteria
      are met — criteria routinely include properties the tests do not cover, such as timing
      budgets, memory ceilings or token cost.
- [ ] `make verify` green.
- [ ] Coverage gates met (§4).
- [ ] Static guards clean, with **zero new exemptions** (§5).
- [ ] No new lint suppressions, type ignores, or skipped tests. If one is genuinely
      unavoidable it carries a reason comment and is called out in the report.
- [ ] Documentation synced **conditionally** per [documentation.md](./documentation.md) — the
      assets the change actually affects, not all of them.
- [ ] On delivery, squash to exactly one conventional commit, per
      [git-workflow.md](./git-workflow.md) §3. Local commits while working are free.
- [ ] Report written: what was built, what was verified, any deviation from the plan and why,
      and anything discovered that should become separate work.

---

## 4. COVERAGE AND TEST SELECTION

- **Two coverage gates, not one.** A single repo-wide number lets well-tested plumbing hide an
  untested core. Set a floor for the whole tree (~80%) and a higher, scoped one for the
  modules that hold the actual logic (~90%).
- **`--strict-markers` and `--strict-config`.** An unregistered marker must fail collection;
  otherwise a typo in `@pytest.mark.integraton` silently disables a test forever and the suite
  stays green while covering less every month.
- **The default run excludes what it cannot trust:** `slow`, `integration`, `perf`, and
  anything marked as needing a live model endpoint. This is the *mechanism* for the rule in
  [SKILL.md](./SKILL.md) §3.2 — without registered markers, "excluded from the default run" is
  a matter of opinion at runtime.
- **Pin the sources of nondeterminism** in a session-wide fixture: seed the RNG, set
  `PYTHONHASHSEED`, and pin BLAS to one thread (`OMP_NUM_THREADS=1`) if the code touches
  numeric libraries. Multi-threaded reduction order is not deterministic, and that eventually
  produces a flaky test that costs a day to diagnose.

---

## 5. STATIC GUARDS

A static guard is a script that reads the source and fails the build on a violation. Write one
for every invariant you cannot afford to have silently re-broken.

### 5.1. How to write one
- **Walk the AST, never regex the source.** Regex gives false positives inside strings and
  comments, and false negatives on aliasing: `f = client.chat; f()` is invisible to a pattern
  match and obvious to an AST walk.
- **Exemptions only by explicit comment**, in the form `# <guard>-ok: <reason>`. The reason is
  mandatory — an unexplained exemption is a silent deletion of the guard.
- **Print every exemption in the summary.** Invisible exemptions accumulate; exemptions
  printed on every run get questioned.
- **Fail with a non-zero exit code**, naming file, line and rule.
- Wire it into `make verify` (the `guards` target) **and** into pre-commit.

### 5.2. The guards this stack needs
| Guard | Enforces | Template |
| :--- | :--- | :--- |
| Provider seam | Provider SDKs are imported and called **only** inside the adapter layer — the mechanical form of the single-interface rule in [SKILL.md](./SKILL.md) §3.2, which is otherwise only prose. | [`check_provider_seam.py`](./templates/check_provider_seam.py) |
| Layering | Module boundaries from [code-design.md](./code-design.md) §1, declaratively. | [`.importlinter`](./templates/.importlinter) |
| `AGENTS.md` drift | In **generated** mode: the root `AGENTS.md` still matches its source (§6). Skip this guard in **opt-out** mode. | [`sync_agents_md.py`](./templates/sync_agents_md.py) |
| Secret shapes | No keys or private keys reach git. | [`.pre-commit-config.yaml`](./templates/.pre-commit-config.yaml) |

### 5.3. Break every guard once
When you install a guard, **violate it deliberately, confirm the build fails, then revert**.
An untested guard is indistinguishable from a guard that does nothing, and installation day is
the only time breaking things is free.

---

## 6. THE ROOT `AGENTS.md`

`AGENTS.md` at the repo root is read automatically by most agents on every session. A skill
module is read only if the agent decides to follow a pointer. Those are different guarantees,
so they carry different content.

- **Prohibitions live inline in `AGENTS.md`.** You consult a *procedure* when you know you need
  it; you need a *prohibition* at the moment you do not know you need it. A pointer works for
  the first case and fails for the second — and the cost of failing is asymmetric. Skipping
  [code-design.md](./code-design.md) means designing worse; skipping guardrail 1 means an
  assertion gets deleted and the report says green.
- **Everything else stays a pointer** to [SKILL.md](./SKILL.md). Procedure, design doctrine,
  the debugging loop and doc-sync are long, situational and cheap to defer.
- **Two adoption modes — pick one and write it in the script `CONFIG`:**
  1. **Generated (+ overlay).** `AGENTS.md` is a projection of §1, §2 and
     [git-workflow.md](./git-workflow.md) §1, delimited here by `agents-md:` markers, plus
     an optional `AGENTS.overlay.md` at the repo root. The overlay is where product rules
     live (read-only targets, ADR-gated deps, metric-logic-in-core). The generator
     concatenates skill blocks + overlay; it never edits the overlay. `--check` runs in
     pre-commit and in `make verify`, and fails when the projection drifts. Edit
     `guardrails.md` or the overlay — never the generated file.
  2. **Opt-out.** The repo keeps a hand-written `AGENTS.md` (playbook distill, product
     rules). Do **not** wire `--check`. Do **not** run the generator. A future agent that
     "helpfully" regenerates will drop product rules. This mode is first-class, not a
     workaround.
- **Keep it under 80 lines.** It is paid for on every session, so length is a real cost.

---

## 7. ERROR CONTRACT

The shape of errors and the exit-code table live in [code-design.md](./code-design.md) §4,
because they are a design contract rather than a check.

The part that belongs here: **a process that exits `0` after failing is a guard that lies to
CI.** Every entry point maps failures onto the documented codes, and no raw traceback reaches
the user unless `--debug` was asked for.
