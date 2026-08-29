# ADR-0005 — float32 accumulation, blocked BLAS, ~1M single-node ceiling

**Status:** Accepted
**Affects:** P2
**Corrects:** source specification defect 2

## Context

Ground truth is the oracle for canary recall and for hubness. If it is wrong, every number the
tool reports is wrong, and wrong in a way that no other test can detect — because everything
else is measured against it.

The source specification described the ground-truth matmul as `float32`/`float16` BLAS. The
`float16` half of that is a correctness bug, not an optimisation. A 768-term dot product
accumulated in half precision has roughly three decimal digits of significand; for normalised
embedding vectors, neighbour similarities routinely agree to four or five digits. Accumulating
in `float16` reorders near-ties, which silently changes which vectors are "the true top 10" —
so the engine gets marked wrong for returning a neighbour that our own oracle mis-ranked.

The scale constraint from the project owner is ~1M vectors × 768 dimensions on a single node.
A 1M × 768 `float32` corpus is 3.07 GB, which fits in RAM on a 16 GB machine but not twice, and
the `Q × N` score matrix at `Q=200` would be another 800 MB if materialised naively — and the
`S × S` hubness matrix at `S=20,000` would be 1.6 GB.

## Decision

- **Accumulation is `float32` minimum, always.** `float16` is permitted as a *storage* format
  (many indexes store half-precision vectors); it is upcast to `float32` on read. `float16`
  never appears in an accumulation.
- **A `float64` cross-check** runs in tests over a small slice, asserting that the `float32`
  path produces the same neighbour ordering. If it ever does not, the tolerance assumption is
  wrong and needs revisiting rather than loosening.
- **Blocked streaming matmul.** Stream corpus blocks of `B` rows; one `sgemm` per block;
  reduce with `argpartition`; merge each block's top-`k` into a running global top-`k`, ties by
  ascending ID. Block size is derived from a `working_set_mb` budget, never hardcoded.
- **Peak additional memory is bounded** by roughly `2 × working_set_mb` beyond the corpus. The
  `Q × N` and `S × S` matrices are never materialised.
- **Cosine** is handled by normalising once at ingest and using dot products, with norms
  asserted within `1e-4` of 1.
- **L2** uses the `‖a‖² - 2a·b + ‖b‖²` expansion with precomputed norms, and **must clamp small
  negative results to zero before `sqrt`.** Floating-point cancellation produces values around
  `-1e-7` for near-identical vectors; unclamped, that becomes `nan` and poisons an entire row of
  ground truth. This is the single most likely silent bug in the whole implementation and it has
  a dedicated test.
- **Block-size invariance is a required test:** identical results for block sizes 1, 7, 999 and
  `n`. Block-boundary errors in the top-`k` merge are the second most likely bug and are
  invisible in aggregate statistics.
- **Determinism:** tests pin BLAS to a single thread, because multi-threaded reduction order is
  not deterministic. If exact cross-threading equality proves impossible, the tolerance is
  measured and documented rather than assumed.
- **The ~1M × 768 ceiling is a deliberate boundary.** Above it, the answer is documented
  sampling with a bootstrap interval, not a distributed compute layer.

## Consequences

**Buys:** an oracle that is trustworthy to the precision it claims, within a predictable memory
envelope, on hardware the target user already has.

**Costs:**
- Roughly 2× the memory traffic of a `float16` path, and no use of half-precision hardware
  acceleration. Accepted without hesitation: the oracle's correctness is not negotiable for a
  constant factor.
- The blocked merge is more code than `argsort` on a full matrix, and it is where the subtle
  bugs live — hence the differential and invariance tests in `P2-04`.
- The 1M ceiling will disappoint someone with a 50M-vector index. Answering that honestly
  ("sampled, with an interval") is better than answering it slowly.

## Alternatives considered

- **`float16` accumulation for speed.** Rejected on correctness, as analysed above.
- **Approximate ground truth via a second ANN index.** Rejected, and worth stating plainly:
  measuring an approximate index against another approximate index measures their disagreement,
  not either one's accuracy. It would produce numbers that look reasonable and mean nothing.
- **Materialising the full score matrix.** Rejected: exceeds the memory budget at the target
  scale, for no benefit over blocking.
- **GPU acceleration now.** Deferred to P10. It changes the determinism guarantees (reduction
  order differs), so it needs its own decision.
- **Faiss for exact search.** Rejected: a large dependency in the base install for something a
  blocked `sgemm` does in fifty lines, plus it would make the oracle depend on a third-party
  implementation rather than on arithmetic we control.

## Revisit if

- Users routinely audit corpora above ~2M vectors, making sampling the default rather than the
  exception.
- A measured need appears for a GPU backend, in which case the determinism invariant must be
  restated before any code is written.
