# P5 — LanceDB Adapter (first real engine)

**Goal:** prove the adapter protocol against a real engine, and reproduce
[`lancedb/lance#4164`](https://github.com/lancedb/lance/issues/4164) as an automated test.

LanceDB is first because it is file-based: no server, no container, no credentials in CI, and
a genuinely read-only access path through PyArrow. It also exposes fragment-level deletion
metadata and IVF index statistics, so four of the five metrics are computable exactly rather
than by proxy.

**Entry criteria:** MVP gate passed (P4 exit checklist).

**Exit gate**

```bash
pytest tests/integration -k lancedb -q      # contract suite + reproduction, zero skips
pytest tests/integration -k readonly -q     # hash/mtime invariance
```

---

## P5-01 — Dataset discovery and descriptor

**Depends on:** P1-02 · **Size:** M · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `tests/integration/test_lancedb_descriptor.py`

**Contract**
- Open a Lance dataset read-only from a path or `lance://` URI; also accept a LanceDB table
  directory and resolve the underlying dataset.
- Detect the vector column: a fixed-size list of `float16`/`float32` in the Arrow schema.
  Multiple candidates → require `--column` and list the options rather than picking one.
- Read `dimension`, `metric_space` and `index_kind` from **index metadata**, never inferred
  from data or supplied by a flag. No index present → `IndexKind.FLAT`, and the audit still
  runs (a flat index has recall `1.0` by definition, which is a useful control and a good
  smoke test of the whole pipeline).
- Populate `Capabilities` honestly for the pinned Lance version.
- Record `engine_version` and the dataset version in the descriptor.

**Guardrail:** the exact API surface for index statistics has changed between Lance releases.
Do not code against remembered signatures. Inspect the pinned version, record what is
actually available in a docstring, and pin a narrow version range (P5-08). Where a needed
datum is absent, the capability is `False` and the metric is `UNAVAILABLE` — not guessed.

**Tests first**
- Descriptor fields correct for fixtures with L2, cosine and dot indexes.
- Ambiguous vector column → `UsageError` listing candidates.
- No index → `FLAT`, audit proceeds, canary recall `1.0`.
- The absolute dataset path is redacted in the descriptor.

---

## P5-02 — Version pinning for a consistent snapshot

**Depends on:** P5-01 · **Size:** S · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `vhecfsck/cli.py`

**Goal:** eliminate the mid-audit mutation problem for this engine entirely.

Lance datasets are versioned and support reading a specific version. A 1M-vector audit takes
minutes, during which a live dataset may be written and compacted — producing the
`snapshot_inconsistent` warning and a slightly-wrong recall figure. Pinning a version makes
the audit read one immutable snapshot from beginning to end.

**Contract**
- `--dataset-version N` pins explicitly; by default, resolve the latest version once at open
  time and hold it for the whole audit.
- The resolved version is recorded in the report, which also makes an audit exactly
  reproducible later.
- If the pinned version has been garbage-collected, fail with exit `4` and a clear message.

**Tests first**
- Writing to the dataset during an audit does not change the audited counts.
- The report records the version; two audits of the same pinned version produce identical
  metric values.

**Acceptance criteria**
- [ ] `snapshot_inconsistent` never appears for a version-pinned LanceDB audit. This is the
      first engine where that warning can be structurally eliminated, and it is worth calling
      out in the docs as a reason LanceDB audits are the most trustworthy.

---

## P5-03 — Exact deletion accounting

**Depends on:** P5-01 · **Size:** M · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `tests/integration/test_lancedb_counts.py`

**Contract**
- Per fragment, obtain physical row count and live row count; the difference is the
  deletion-file population. Aggregate to `IndexCounts` with `exact = True`.
- Report the **per-fragment distribution**, not only the total. A single pathological
  fragment among a hundred healthy ones is invisible in an aggregate ratio and is exactly the
  case that triggers a compaction decision.
- `indexed` count from index statistics where available, so "rows not yet in the index" is
  distinguishable from "rows deleted" — the same conflation trap documented for Qdrant in
  [`02-metrics-spec.md §4.2`](../../02-metrics-spec.md).

**Tests first**
- Fixture with a known number of deleted rows → DFI matches exactly.
- Deletions concentrated in one fragment → per-fragment distribution shows it.
- A dataset with no deletions → DFI exactly `0.0` with `exact = True` (distinct from
  `UNAVAILABLE`).

---

## P5-04 — Vector enumeration and random access

**Depends on:** P5-01 · **Size:** M · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `tests/integration/test_lancedb_scan.py`

**Contract**
- `iter_live_vectors` via a projected Arrow scan of the vector column plus row ID, in
  batches, zero-copy into NumPy where the Arrow buffer allows it. `float16` storage is upcast
  to `float32` on read ([ADR-0005](../../adr/0005-ground-truth-precision-and-blocking.md)).
- `fetch_vectors(ids)` via a `take` on row IDs, returning rows in the requested order.
- Deleted rows are excluded from enumeration. Reading tombstoned vectors for the visualizer's
  grey layer is capability-gated: if the pinned version cannot expose them, the capability is
  `False`, and P4's tombstone layer degrades to a count badge rather than fabricating points.
- Batch size derived from the memory budget, not hardcoded.

**Tests first**
- Enumeration yields exactly `counts().live` rows with unique IDs and no deleted IDs.
- `sample_ids → fetch_vectors` round-trips bit-exactly against enumeration.
- `float16` datasets produce `float32` output with the expected values.
- A 1M-row fixture enumerates within the memory budget (marked `slow`).

---

## P5-05 — Engine search

**Depends on:** P5-01 · **Size:** M · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `tests/integration/test_lancedb_search.py`

**Contract**
- Batched k-NN through the engine's own search path, honouring `nprobe` and `refine_factor`,
  with the **effective** parameters echoed into `SearchResult.effective_params` — including
  the engine defaults when the user specified nothing. A recall number without its
  `nprobe` is not interpretable, and defaults change between versions.
- Never enable a flag that makes search exact or post-verified unless the user explicitly
  asked. The point is to measure the engine as it is actually configured in production, not
  to make it look good.
- Engine-reported distances are captured for diagnostics but **never** used for recall
  scoring ([`02-metrics-spec.md §2.2`](../../02-metrics-spec.md)).
- Batch queries; fall back to a loop if the pinned version lacks batch search, with the
  slower path noted in the report's timings.

**Tests first**
- Recall increases monotonically with `nprobe` on a fixture with a known-degraded index.
- `effective_params` is populated even when the user passes nothing.
- On a flat (unindexed) dataset, recall is `1.0` — the end-to-end proof that our ground truth
  agrees with an exact engine scan. If this fails, the bug is in `core/`, not the adapter.

---

## P5-06 — IVF partition introspection

**Depends on:** P5-01 · **Size:** M · **Touches:** `vhecfsck/adapters/lancedb_adapter.py`, `tests/integration/test_lancedb_partitions.py`

**Contract**
- Obtain per-partition row counts from index statistics. If only `num_partitions` is exposed
  without per-partition sizes, the capability is `False` and `partition_size_cv` is
  `UNAVAILABLE` — computing partition assignments ourselves by re-running k-means would be
  measuring *our* clustering, not the index's, and would be a fabricated metric.
- Set `partition_live_counts` honestly; if sizes include deleted rows, set
  `includes_deleted = True` so the metric reports it.
- For `IVF_PQ`, also record `num_sub_vectors` and the quantisation kind in the descriptor —
  context a reader needs to interpret a recall figure.

**Tests first**
- A deliberately imbalanced fixture yields a CV matching a direct computation over the true
  assignment.
- A non-IVF dataset → `UNAVAILABLE(not_applicable)`, not a failure.
- A single-partition index → `UNAVAILABLE` per the spec guard.

---

## P5-07 — Read-only verification harness

**Depends on:** P5-04, P5-05 · **Size:** M · **Touches:** `tests/integration/test_readonly_lancedb.py`, `tests/conftest.py`

**Goal:** turn the read-only claim into evidence. This is the ticket that makes the claim in
`SECURITY.md` defensible.

**Contract**
- A reusable fixture that snapshots a directory tree — every file's size, mtime, and SHA-256
  — runs an arbitrary callable, and re-snapshots.
- Applied to a full audit including search, enumeration, partition introspection and
  projection: assert **zero** differences, including no new files (a stray `_versions` entry
  or index cache counts as a violation and must be investigated, not tolerated).
- Also run the audit against a directory mounted read-only (`chmod -R a-w`) to prove no write
  is even attempted — a genuinely independent check, since a write that fails silently would
  still pass the hash comparison if the engine swallowed the error.

**Tests first**
- Full audit → zero filesystem deltas.
- Full audit against a read-only directory → succeeds.
- A deliberately injected write (in a test-only branch) makes the harness fail, proving the
  harness detects what it claims to.

**Acceptance criteria**
- [ ] The harness is generic enough to be reused for any file-backed engine.
- [ ] It runs in the default CI job, not only nightly. This invariant is too important to
      check once a day.

---

## P5-08 — Version compatibility matrix

**Depends on:** P5-01 · **Size:** S · **Touches:** `pyproject.toml`, `.github/workflows/nightly.yml`, `docs/engines/lancedb.md`

**Contract**
- Pin a tested range for `lance` / `lancedb` in the `lancedb` extra.
- The adapter detects the runtime version and warns once when outside the tested range,
  rather than failing — a user on a newer version should get a caveat, not a wall.
- The nightly workflow installs the newest release and reports breakage as an issue
  ([risk R4](../../risk-register.md)).
- `docs/engines/lancedb.md` records which capabilities are available at which version, and
  which metrics are consequently `UNAVAILABLE`.

**Acceptance criteria**
- [ ] Tested versions listed in the docs and asserted in CI.
- [ ] An out-of-range version produces one warning, not one per call.

---

## P5-09 — Reproduce `lance#4164`

**Depends on:** P5-06, P5-05 · **Size:** M · **Touches:** `tests/integration/test_repro_lance_4164.py`, `docs/scenarios/lance-4164.md`

**Goal:** the headline evidence that the tool detects a real, documented production failure.

**Contract**
- Build a dataset, create an IVF index with a `num_partitions` appropriate to the initial
  size, then append roughly 10× more rows **without** re-indexing.
- Assert the pathology is real before asserting we detect it: query latency and/or scanned
  rows grow materially, and recall at fixed `nprobe` degrades. A test that only asserts our
  own metric moved would prove nothing about the world.
- Assert `vhecfsck` reports `partition_size_cv` above the warn threshold and a canary recall
  drop, and exits non-zero.
- Assert the counterfactual: after rebuilding the index on the grown dataset, the metrics
  return to healthy. Without this, the test could be passing for an unrelated reason.
- Document the scenario in `docs/scenarios/` with the reproduction steps, the observed
  numbers, and a link to the upstream issue.

**Tests first** — the assertions above, marked `integration` and `slow`, sized to run in CI in
under two minutes.

**Acceptance criteria**
- [ ] Deterministic and non-flaky over ten consecutive runs.
- [ ] The documented numbers were measured, not estimated. Any number in the docs that nobody
      measured is a liability at launch.

---

## P5-10 — LanceDB user guide

**Depends on:** P5-09 · **Size:** S · **Touches:** `docs/engines/lancedb.md`, `README.md`

**Contract**
- Quickstart: audit an existing dataset in one command.
- Capability table: which metrics are exact, which are proxies, which are unavailable, and
  why.
- The version-pinning recommendation from P5-02 and why it matters.
- The read-only evidence: what P5-07 verifies, so a reviewer can check the claim rather than
  trust it.
- Guidance on choosing `--queries` from a real query log, and the honest caveat that
  corpus-drawn queries yield an optimistic recall bound.

---

## Phase exit checklist

- [ ] Contract suite green against `LanceDbAdapter` with zero skips.
- [ ] Read-only harness shows zero filesystem deltas, and passes against a read-only mount.
- [ ] `lance#4164` reproduced, detected, and reverted-to-healthy in an automated test.
- [ ] Deletion accounting exact, with a per-fragment breakdown.
- [ ] `snapshot_inconsistent` structurally impossible under version pinning.
- [ ] The `IndexAdapter` protocol needed no breaking change. If it did, amend
      [ADR-0013](../../adr/0013-adapter-protocol.md) with what was missed and why — that lesson
      is the main transferable output of this phase.
