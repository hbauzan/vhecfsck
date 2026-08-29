# ADR-0013 — Structural Protocol with honest capabilities

**Status:** Accepted
**Affects:** P1, P5, P7, P10

## Context

The tool must eventually support engines with radically different access models: a local
columnar file format (Lance), an HTTP/gRPC server (Qdrant), a relational database with an index
extension (pgvector), and later others. What each engine can tell us about itself varies enormously
— Lance exposes exact per-fragment deletion counts, pgvector offers only table-level statistical
estimates, and neither exposes HNSW graph structure.

Two design failures are available here, and both are common.

The first is **the lowest common denominator**: define the interface as only what every engine can
do, and lose the exact deletion counts LanceDB happily provides. The tool becomes uniformly weak.

The second is worse, and is the one this project must actively guard against: **substituting the
available number for the correct one.** When Qdrant does not expose segment-level deleted counts,
`points_count` versus `indexed_vectors_count` is right there and looks like a fragmentation ratio.
It is not one — it also excludes vectors in segments below the indexing threshold, so it reports
fragmentation on a freshly loaded, perfectly clean collection. Shipping that would mean confidently
reporting a number that means something other than what the label says, which is the most damaging
kind of bug this tool could have.

## Decision

**A structural `Protocol`, not an abstract base class.** `@runtime_checkable`, structurally typed,
verified by `mypy --strict`. A third party can implement an adapter without importing our class
hierarchy or inheriting behaviour they did not ask for.

**Explicit, opt-in `Capabilities`.** Every optional read is gated by a boolean that defaults to
`False`:

```text
enumerate_vectors, random_access_by_id, report_deleted_counts, deleted_counts_exact,
report_partitions, partition_live_counts, report_graph_stats, search_params_settable,
filtered_search
```

Defaulting to `False` means forgetting to declare a capability degrades a metric to
`UNAVAILABLE` — the safe direction. The unsafe direction, where a forgotten declaration produces a
plausible wrong number, is unreachable by construction.

**Capability honesty is a hard rule.** If the correct datum is unobtainable, the capability is
`False` and the metric is `UNAVAILABLE`
([ADR-0004](0004-metric-result-states-and-exit-codes.md)). Substituting a differently-defined
number that happens to be available is prohibited, and the Qdrant DFI case above is documented in
[`02-metrics-spec.md §4.2`](../02-metrics-spec.md) as the worked example of the rule.

**No write methods exist**, per [ADR-0001](0001-read-only-by-default.md). Not disabled — absent.
A test asserts none of the denylisted write names appears on the protocol, so a future addition
fails loudly.

**Exactness is carried, not assumed.** `IndexCounts` and `PartitionStats` carry `exact`,
`estimated`, `proxy` and `includes_deleted` flags. These propagate into `evidence_strength` and
into the report, so a user always knows whether a number is a measurement or an approximation.

**The shared contract suite** (`tests/contract/`) is the definition of a working adapter. Every
adapter passes it unmodified. For every `False` capability, the suite verifies the `UNAVAILABLE`
path rather than skipping — unsupported capabilities are tested, not ignored.

**Search parameters are echoed, never silently defaulted.** `SearchResult.effective_params`
reports what was actually used, including engine defaults when the user specified nothing. A
recall figure without its `nprobe` or `ef_search` is not interpretable, and defaults change
between engine versions.

## Consequences

**Buys:** each engine contributes its best available data without dragging the others down.
Adding an engine is bounded work with an objective completion criterion — the contract suite
passes. Users can see exactly which numbers are exact and which are proxies, per engine, in the
published capability matrix.

**Costs:**
- The capability matrix is a support surface. Users will ask why a metric is unavailable on their
  engine, which is why every `UNAVAILABLE` reason must name the missing capability and the
  version or privilege that would supply it (`P8-09`).
- More `None`-returning optional methods than a rigid interface would have, and more branches in
  the pipeline.
- Protocols cannot supply shared implementation. Common helpers live as free functions in
  `adapters/base.py`, which is slightly less discoverable than inherited methods.
- The protocol was designed before any real engine existed, so it may be missing something. That
  is exactly what `P5` is for: if LanceDB forces a protocol change, the change is **amended into
  this ADR** with an explanation of what was missed, because that lesson is the most transferable
  output of the first real adapter.

## Alternatives considered

- **Abstract base class with `NotImplementedError` stubs.** Rejected: capability discovery becomes
  exception-driven, and the failure mode of a forgotten override is a runtime crash rather than a
  clean `UNAVAILABLE`.
- **Lowest-common-denominator interface.** Rejected: throws away exact data that some engines
  provide, making the tool uniformly weaker than necessary.
- **Capabilities inferred by probing at runtime** (try it and catch the exception). Rejected:
  slow, fragile across versions, and it conflates "unsupported" with "transiently failing".
- **One adapter class per engine with no shared interface.** Rejected: no contract suite, so no
  objective definition of a correct adapter, and every metric would need per-engine branching.

## Revisit if

- `P5` or `P7` reveals a required read that the protocol cannot express — amend, do not silently
  extend.
- A fourth engine class appears (for example, a managed service with a fundamentally different
  access model) that the current shape cannot accommodate.
