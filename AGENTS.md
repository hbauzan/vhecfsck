# Agent operating rules

Read this on every session. Detail lives in [`roadmap/`](roadmap/); this file is the
non-negotiable subset.

**Roadmap:** [`roadmap/agent-playbook.md`](roadmap/agent-playbook.md) ·
[`roadmap/02-metrics-spec.md`](roadmap/02-metrics-spec.md) ·
[`roadmap/backlog.md`](roadmap/backlog.md)

## The gate

Three moments. Do not collapse them.

| When | Command |
| :--- | :--- |
| While coding (TDD) | `uv run pytest` on the tests you are writing, plus a neighbour if the seam is next door. `make test` if you want the uninstrumented default suite. |
| Ticket ready to merge | `make verify` **once**. Coverage **is** the suite (do not also run `make test` as a gate step). |
| Version tag / `verify-full` | `make verify-full`. Always, however long it takes. |

```bash
make verify
```

Green or the ticket is not finished. Never `--no-verify`. Never "green except a pre-existing
failure" — that failure is a finding to report. Do not run `make verify` just because you
pulled `main`.

## Hard guardrails

Violating one means the work is wrong **regardless of whether the tests pass**.

1. **Never weaken a test to make it pass** — not a loosened tolerance, skip, `xfail`, or
   deleted assertion. A wrong test is a finding with evidence, not a unilateral edit.
2. **Never add a dependency without an ADR.** Transitive convenience counts; front-end too.
3. **Never write to an audited target.** No exceptions, including tests. Pathology fixtures
   live in the harness, outside the package ([ADR-0001](roadmap/adr/0001-read-only-by-default.md)).
4. **Never leave `make verify` red.** "I'll fix it next commit" is how red becomes permanent.
5. **Never exceed the ticket's declared scope.** Out-of-scope bugs become new tickets.
6. **Never bypass a guard.** No `# type: ignore` / `# noqa` without a reason comment; no
   silent exclusion-list edits.
7. **Never guess at an ambiguous specification** — especially numeric. Stop and ask.
8. **Never use the global RNG or unordered iteration** for anything that reaches output.
9. **Never write a number into documentation that nobody measured.**
10. **Never code against a remembered API** — inspect the pinned version.
11. **Never put metric logic outside `core/`.**
12. **Never report a number you could not compute** — `UNAVAILABLE` with a reason, always.

## Delivery

- One ticket, one branch, one conventional commit (squash on delivery).
- Branch/commit freely while working. **Never push or merge to `main` without an explicit
  OK** from the human ("ok", "dale", "mergealo"). Silence is not approval.
- On OK: squash to one conventional commit, then merge to `main`.
- Report how to test, then wait.

## Tooling

- Python deps only via `uv` (never `pip` / manual venv).
- Product = read-only CLI auditor. Hero: `uvx vhecfsck demo`. No daemon, no SaaS.
- `setup.sh` is a macOS contributor panel, not the product.
