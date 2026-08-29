<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Source: .agents/skills/dev-protocol/guardrails.md and git-workflow.md
     Regenerate: uv run python scripts/sync_agents_md.py
     Verified by `make verify`; editing this file directly will fail the gate. -->

# Agent operating rules

The full protocol lives in [`.agents/skills/dev-protocol/SKILL.md`](.agents/skills/dev-protocol/SKILL.md). The rules below
are copied here because they must apply even if you never open it.

## The gate

```bash
make verify        # lint + format-check + typecheck + test + coverage + guards
```

- **Green or you are not finished.** Not "green except a pre-existing failure". If something
  unrelated is broken, that is a finding to report, not a licence to proceed.
- **Never bypass it.** No `--no-verify`, no running a subset and calling it verified.

## Hard guardrails

Violating one of these means the work is wrong **regardless of whether the tests pass**.

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

## Delivery

- Branch, stage and commit **locally** as freely as you like while working.
- **Never `git push` and never merge to the base branch** until the user has verified the change and given an **explicit go-ahead** ("ok", "dale", "andá", "mergealo"). Silence, a thumbs-up on something unrelated, or the absence of objection is **not** approval.
- Reporting "ready to test" and then **waiting** is mandatory, not optional politeness.

One commit per logical task, conventional message:

```yaml
Branch Name: <type>/<short-descriptive-name>  # e.g. feat/provider-fallback
Commit Message: <type>(<scope>): <short description in present tense>
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `build`, `ci`, `chore`. The body
says **why**, not what — the diff already says what.

## Everything else

Read [`SKILL.md`](.agents/skills/dev-protocol/SKILL.md) first (role, style, environment, idea-to-delivery
flow). Open a module only when the task calls for it:

| Task | Module |
| :--- | :--- |
| design, TDD, error contract | `code-design.md` |
| a bug or a red test | `debugging.md` |
| verifying, closing, installing a guard | `guardrails.md` |
| reviewing a diff, filing issues | `qa-review.md` |
| committing, hooks, delivery | `git-workflow.md` |
| a contract or doc changed | `documentation.md` |
| arriving cold, designing from scratch, debug Phase 3 | `lessons-learned.md` |

Hard toolchain rule: Python dependencies go through `uv`. Never `pip install`, never a
manually activated venv.
