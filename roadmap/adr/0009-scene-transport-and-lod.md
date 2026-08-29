# ADR-0009 — Binary scene transport with class-stratified LOD

**Status:** Accepted
**Affects:** P4, P6
**Corrects:** source specification defect 8

## Context

The showcase renders the index topology in 3D. At the project's target scale that means up to
1M points, each needing three `float32` coordinates plus a class and an ID.

As JSON, one point is roughly 60–120 bytes of text (`{"x":0.123456,"y":-0.98765,...}`), so a
1M-point scene is 60–120 MB of JSON that then has to be parsed into JavaScript numbers and
copied into typed arrays. The parse alone would freeze the tab for seconds and the peak memory
would be several times the final buffer size. As raw `float32` buffers the same scene is 12 MB
of positions plus 1 MB of classes — a 10× reduction with zero parsing.

The decimation question is equally load-bearing and less obvious. A browser will not hold 60 fps
at 1M points on integrated graphics, so the scene must be thinned. But the points that matter
most are the rarest: with a hub share of 20%, the top 1% of vectors are a few thousand points out
of a million. Uniform random sampling to a 200k budget would retain about one in five of them —
so the tool would compute a correct finding and then randomly discard four fifths of the evidence
before drawing it. The visualization would be pretty and would fail at its only job.

## Decision

**Transport.** A small JSON header (counts, dtypes, buffer offsets, LOD metadata, colour legend)
followed by concatenated raw little-endian typed-array buffers, served as
`application/octet-stream`. The client wraps buffers in typed arrays with no parsing and no copy,
and uploads them straight to the GPU. Endianness is asserted explicitly rather than assumed.
Compression via standard `gzip`/`zstd` content negotiation only — never a bespoke scheme.
A `json-scene` debug format exists for inspecting small scenes and is documented as unsuitable
for large ones.

**Level of detail.** `decimate(scene, budget, seed)` with **class-stratified** retention:

1. Every `HUB`, `ANTIHUB` and `QUERY` point is retained, up to a generous per-class cap. The
   findings are never sampled away.
2. `HEALTHY` points absorb the remaining budget, thinned with spatial awareness — one point per
   occupied voxel first, then random fill — so the corpus keeps its visual shape instead of
   dissolving into uniform noise.
3. Deterministic under a fixed seed.
4. Per-class retention ratios and the total are recorded in the payload, and the UI displays
   "showing 200,000 of 1,043,133 points (class-stratified)".

**Progressive delivery** (P6-01): a coarse scene first so something renders immediately, then
refinement chunks. Hubs and anti-hubs arrive in the **first** chunk — the findings should be
visible before the background is.

**Honesty rules.** The displayed count and the true count are always both shown. Tombstones are
never given fabricated positions when the adapter cannot read deleted vectors; the UI shows a
count and an explanation instead. The projection's `explained_variance_ratio` is displayed
prominently, because a 3D view of 768 dimensions typically retains 10–25% of the variance and
presenting it as the truth would be the most misleading thing this interface could do.

## Consequences

**Buys:** a scene that loads in under a second, renders at 60 fps, and never hides a finding
behind a sampling decision. The UI states its own lossiness rather than implying completeness.

**Costs:**
- Two implementations of the codec (Python encoder, TypeScript decoder) that must agree. Mitigated
  by testing both against one shared fixture artifact rather than against each other's
  assumptions.
- Buffer alignment matters: a misaligned offset throws on `Float32Array` construction, in a way
  that is genuinely unpleasant to debug from a browser stack trace. Explicitly tested.
- The scene payload is not human-readable, so debugging needs the `json-scene` escape hatch.
- Stratified sampling means the displayed class proportions are **not** the true class
  proportions. This must be stated in the UI, or a viewer will read the visible hub density as
  the hub share. The number in the HUD is the metric; the picture is an illustration.

## Alternatives considered

- **JSON scene payload.** Rejected on size and parse cost, as analysed.
- **Arrow IPC.** Genuinely attractive — PyArrow is already a dependency for LanceDB, and the
  format is well specified. Rejected for the client side: it would add an Arrow JavaScript
  dependency to the bundle to decode three flat numeric arrays. Reconsider if the payload ever
  becomes structurally complex.
- **glTF / point-cloud formats (PLY, LAS).** Rejected: designed for geometry interchange, carry
  metadata we do not need, and still require a parser.
- **Uniform random decimation.** Rejected: discards the findings, as analysed above. This is the
  decision most likely to be "simplified" by a future contributor who has not read this ADR.
- **Client-side decimation of the full payload.** Rejected: requires transferring 1M points to
  discard 80% of them in the browser.

## Revisit if

- Scene payloads grow structurally complex enough that Arrow IPC's schema handling would pay for
  its bundle cost.
- WebGPU compute makes client-side decimation of a full-resolution payload cheap enough that
  transferring everything becomes reasonable.
