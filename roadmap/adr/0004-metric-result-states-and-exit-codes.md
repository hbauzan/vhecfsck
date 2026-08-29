# ADR-0004 — Tri-state plus UNAVAILABLE; six exit codes

**Status:** Accepted
**Affects:** P0, P2, P3
**Corrects:** source specification defects 5 and 6

## Context

The source specification defined three states (`OK` / `WARN` / `FAIL`) and three exit codes
(`0` / `1` / `2`). Both are one concept short, in the same way, and the omission is dangerous
rather than merely incomplete.

**The missing state.** Not every metric is computable against every engine. Qdrant may not
expose segment-level deleted counts; a flat index has no partitions; a 500-vector corpus is too
small for the hubness guards. With only three states, an unavailable metric has to be encoded as
something — and the tempting encoding is `OK` with a value of `0.0`, which for DFI means
"perfectly clean index". The tool would report perfect health precisely when it knows nothing.

**The missing code.** With only `0/1/2`, a crash, a typo in a flag, and an unreachable database
all have to collapse into one of those three. If they map to `2` (`FAIL`), then a misspelled
flag reports a broken index. If they map to `1`, real failures get muted. Either way the CI
signal becomes untrustworthy, and the standard response to an untrustworthy check is `|| true`.

## Decision

**Five metric states:**

| State | Meaning |
| :--- | :--- |
| `OK` | Computed, healthy |
| `WARN` | Computed, crossed the warn threshold |
| `FAIL` | Computed, crossed the fail threshold |
| `UNAVAILABLE` | Could not be computed — carries a reason, never a value |
| `DISABLED` | Explicitly turned off in configuration |

The `MetricResult` constructor enforces the invariant: `UNAVAILABLE` requires `value is None`
**and** a non-empty `unavailable_reason`; the three computed states require a value. Making the
illegal combination unconstructible is what turns this ADR from a convention into a guarantee.

**Six exit codes:**

| Code | Meaning |
| :--- | :--- |
| `0` | `OK` |
| `1` | `WARN` |
| `2` | `FAIL` |
| `3` | `INCONCLUSIVE` — the audit ran but a verdict could not be established |
| `4` | Usage, configuration or connection error |
| `70` | Internal error (unhandled exception) |

`70` follows the `sysexits.h` convention for `EX_SOFTWARE`. `--strict-unavailable` promotes
`UNAVAILABLE` to `FAIL` for pipelines that would rather block than proceed on partial
information.

**Rendering rules, which are the part that actually protects users:**
- Terminal: `UNAVAILABLE` uses a distinct glyph and colour from `OK`, with the reason inline.
- Prometheus: the value gauge is **omitted entirely** and `vhecfsck_metric_unavailable{metric}`
  is set to `1`. A dashboard then shows a gap rather than a plausible number, and a staleness
  alert can fire.
- JSON: `value` is `null`, never `0`.

## Consequences

**Buys:** unknown never looks like healthy, in any output format. CI can distinguish "your index
is broken" from "the checker could not tell", which is the difference between a check people
trust and a check people disable.

**Costs:**
- Five states multiply the verdict-aggregation truth table, which is why `P2-09` requires 100%
  branch coverage on that one small module.
- Users will encounter `UNAVAILABLE` and be mildly annoyed. Mitigated by requiring every reason
  string to name the missing capability and, where possible, the privilege or version that would
  supply it (`P8-09`).
- Six exit codes is more than most tools, and needs documenting in every CI recipe.

## Alternatives considered

- **`UNAVAILABLE` as a report warning rather than a metric state.** Rejected: warnings are
  ignored, and the metric would still need some state, bringing back the original problem.
- **Mapping `UNAVAILABLE` to `WARN`.** Rejected: conflates "I don't know" with "I found
  something", and would train users to ignore warnings.
- **Only `0` and non-zero.** Rejected: loses the WARN tier that lets teams adopt the tool
  gradually without blocking their pipeline on day one.
- **`3` for internal errors instead of `70`.** Rejected: `sysexits` conventions exist and cost
  nothing to follow.

## Revisit if

Real usage shows `UNAVAILABLE` is so common on a major engine that it dominates the output — in
which case the fix is more adapter capability, not fewer states.
