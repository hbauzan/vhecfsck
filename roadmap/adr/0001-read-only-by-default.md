# ADR-0001 — Strictly read-only, enforced structurally

**Status:** Accepted
**Affects:** every phase, every module

## Context

`vhecfsck` connects to production vector databases. The adjacent tools it is compared to —
`fsck`, `VACUUM`, index rebuild utilities — all write, and users will assume this one might
too. That assumption is the main barrier to installation: a platform engineer will not point an
unfamiliar tool at their production PostgreSQL if there is any chance it mutates something.

The asymmetry is brutal. Read-only correctness buys trust slowly; one incident of data
corruption ends the project permanently and no amount of subsequent care recovers it. There is
no version of this tool that is worth that risk, and no feature worth relaxing the rule for.

A softer version of this rule — "we don't write, we just don't have a flag for it" — is not
enough. Code changes, contributors are unfamiliar with intent, and an engine SDK method that
looks like a read can trigger a compaction as a side effect.

## Decision

Read-only is enforced at five independent layers, not asserted in documentation:

1. **Structural.** The `IndexAdapter` protocol declares no write methods. There is nothing to
   call, so there is nothing to call by accident.
2. **Static.** An AST-based check (`P0-09`) fails the build on any call to a denylisted write
   API, or any SQL-shaped string containing `VACUUM`, `REINDEX`, `DELETE`, `UPDATE`, `INSERT`,
   `TRUNCATE` or `ALTER`, anywhere in `adapters/` or `core/`. Exemptions require an inline
   `# readonly-ok: <reason>` comment and are listed in the check's output so they stay visible.
3. **Session-level.** Where the engine supports it, the connection itself refuses writes:
   PostgreSQL sessions run with `default_transaction_read_only = on` inside an explicitly
   read-only transaction. Rejection by the server is stronger than absence in our code.
4. **Empirical.** Integration tests hash and stat the entire target before and after a full
   audit and assert zero deltas, including no new files. Audits also run against a
   filesystem mounted read-only, which catches a write that an engine might swallow silently.
5. **Documented.** `SECURITY.md` treats a hypothetical write path as a security vulnerability
   with a private reporting channel, not as an ordinary bug.

Remediation is permanently out of scope. A future `--advise` mode may *print* the command an
operator could run; it will never run it.

## Consequences

**Buys:** the tool is installable in environments that would reject anything else. The
guarantee is verifiable by a skeptical reviewer rather than merely claimed, which is the only
form of trust that matters to this audience.

**Costs:**
- Some metrics are simply unobtainable. Partition assignments that an engine does not expose
  cannot be recomputed by us without measuring our own clustering instead of the index's, so
  the metric is `UNAVAILABLE`. We accept a less complete tool over a more complete but invasive
  one.
- No `VACUUM` before measuring, which means pgvector DFI is a table-level proxy rather than an
  exact index-level count.
- Test helpers that need to mutate a target (to *create* a pathology) live in the test harness
  and are architecturally separated from the package, which adds friction — deliberately, since
  a convenient write helper inside the package is exactly how this invariant erodes.

## Alternatives considered

- **Read-only by default with an opt-in `--allow-write` flag.** Rejected. The flag's existence
  requires write code paths to exist, which defeats layer 1 entirely. It also invites feature
  requests that pull the project toward being a repair tool.
- **A "dry-run" mode that prints what it would change.** Rejected as a framing: it implies a
  write mode is coming. `--advise` (print a suggested operator command) achieves the useful part
  without the implication.
- **Documentation-only guarantee.** Rejected. Unverifiable by the audience that most needs it.

## Revisit if

Never, for the core invariant. The five-layer enforcement mechanism may be strengthened or
made cheaper; the guarantee itself is not open for reconsideration. A proposal to add any
write path should be treated as a proposal for a different product.
