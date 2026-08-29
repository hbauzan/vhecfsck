# ADR-0008 — The report is a versioned public contract

**Status:** Accepted
**Affects:** P3, P4, P7, P9

## Context

The JSON report is not an implementation detail. Within weeks of release it will be parsed by
CI scripts, stored in artifact buckets, diffed between runs, fed into dashboards, and pasted
into issue trackers. Any change to its shape breaks somebody's pipeline silently — their `jq`
expression returns `null`, their gate stops firing, and nobody notices until an outage.

The report is also the only interface between the audit engine and both front ends. If the
terminal renderer or the 3D visualizer can reach around it for "just one more number", the
architecture's central rule dissolves and metric logic starts appearing in a shader.

## Decision

- **`schema_version` is a top-level field**, distinct from `tool_version`. The tool may release
  freely; the schema changes deliberately.
- **Change policy:** additive changes (new optional field, new metric, new `detail` key) bump the
  minor version. Removals, renames, or semantic changes to an existing field bump the major
  version and require a migration note in `CHANGELOG.md`. Stable from `v0.1.0`, notwithstanding
  the `0.x` version of the tool itself.
- **A JSON Schema is generated from the model and committed** to `schema/report-1.0.json`, with a
  CI drift check that fails if the model and the committed schema diverge. This is what makes the
  schema a contract rather than stale documentation.
- **Golden-file tests** cover every scenario, with volatile fields normalised by a shared helper.
  Any unplanned change to the emitted structure fails the build and shows the diff in the pull
  request.
- **Consumers:** `vhecfsck export` accepts older minor versions and refuses a newer major version
  with a clear message rather than mis-parsing it.
- **The report is the only channel to the front ends.** Both renderers and the visualizer consume
  it and nothing else. If the visualizer needs a derived value, it is added to the schema — which
  is precisely why the 3D slice is built in P4, early, rather than after the schema has
  ossified.
- **Deterministic serialisation:** sorted keys, fixed float precision applied at the
  serialisation boundary, `\n` endings, trailing newline. Never `NaN` or `Infinity`, which are
  not valid JSON and cause a strict parser to reject the entire document.
- **Nothing sensitive may enter a report:** no credentials (locations are redacted), no raw
  vectors, no document text. A test audits a corpus seeded with a recognisable secret and greps
  the serialised output.

## Consequences

**Buys:** users can build on the output safely. Schema changes become visible, reviewable events
rather than accidents. The architecture's layering rule has a concrete enforcement point.

**Costs:**
- Adding a field requires touching the model, the committed schema, and the golden files. That
  friction is the feature; it is what makes an accidental change impossible.
- Deterministic float formatting means slightly lossy serialisation at a documented precision.
  Accepted: byte-identical reproducibility across platforms is worth more than the last digit of
  a recall value, and the rounding happens only at the output boundary, never in computation.
- We are committing to schema stability before knowing every field we will eventually want, which
  is exactly why the visualizer, the Prometheus exporter and the baseline comparison are all
  designed against the schema early — P4-02, P3-06 and P3-01 respectively each exist partly to
  pressure-test the schema before it is frozen.

## Alternatives considered

- **No versioning; treat output as unstable.** Rejected: users will depend on it regardless, and
  telling them not to is not a strategy.
- **Version the tool only.** Rejected: couples schema stability to release cadence, so a patch
  release could break a parser.
- **Protobuf or Avro.** Rejected: JSON is what `jq`, CI systems and humans consume. Binary
  framing is used only where volume demands it — the scene payload
  ([ADR-0009](0009-scene-transport-and-lod.md)) — and that is not a stable public contract.
- **Let the visualizer call `core/` directly for extra data.** Rejected: this is the exact
  failure this ADR exists to prevent, and it starts with one reasonable-sounding exception.

## Revisit if

A major version bump becomes necessary. At that point, ship a conversion utility rather than
expecting users to migrate their own stored reports.
