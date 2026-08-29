# P1 — Synthetic Corpus and Adapter Protocol

**Goal:** build the target before building the instrument.

This phase produces a vector index we fully control — one whose true DFI, true partition
sizes, true hub structure and true recall are known by construction — plus the protocol that
every real engine will later have to satisfy. Doing this first means that when LanceDB
eventually disagrees with a metric in P5, there is exactly one suspect.

**Entry criteria:** P0 exit checklist complete.

**Exit gate**

```bash
pytest tests/contract tests/unit -q && make verify
```

The contract suite must pass against `SyntheticAdapter` with **zero skips**.

---

## P1-01 — Shared domain types

**Depends on:** P0-07 · **Size:** M · **Touches:** `vhecfsck/models/target.py`, `vhecfsck/models/corpus.py`, `tests/unit/test_models.py`

**Goal:** a leaf package of types that everything imports and that imports nothing internal
([`01-architecture.md §4`](../01-architecture.md)).

**Contract**
- `MetricSpace` enum: `COSINE`, `L2`, `DOT`.
- `IndexKind` enum: `FLAT`, `IVF`, `IVF_PQ`, `HNSW`, `HNSW_PQ`, `UNKNOWN`.
- `TargetDescriptor`: engine, engine version, index kind, index name, redacted location,
  dimension, metric space.
- `Capabilities`: explicit booleans — `enumerate_vectors`, `random_access_by_id`,
  `report_deleted_counts`, `deleted_counts_exact`, `report_partitions`,
  `partition_live_counts`, `report_graph_stats`, `search_params_settable`,
  `filtered_search`. Defaults are all `False`: an adapter must opt in to each claim, so
  forgetting to declare a capability degrades a metric to `UNAVAILABLE` rather than silently
  producing a wrong number.
- `IndexCounts`: `live`, `deleted`, `total`, `indexed`, `degenerate`, `exact: bool`,
  `read_at: datetime`.
- `VectorBatch`: `ids: NDArray[int64]`, `vectors: NDArray[float32]` (C-contiguous, shape
  `(n, d)`), with a validating constructor.
- `SearchResult`: `ids: NDArray[int64]` shape `(q, k)` with `-1` padding for short returns,
  `distances: NDArray[float32] | None`, `effective_params: dict`.
- `PartitionStats`: `sizes: NDArray[int64]`, `includes_deleted: bool`, `n_partitions`.
- `GraphStats`: `in_degree_histogram`, `entry_point_ids`, `entrypoint_tombstoned: bool | None`.

**Tests first**
- `VectorBatch` rejects non-`float32`, non-contiguous, wrong-rank, and `ids`/`vectors`
  length mismatches.
- `Capabilities()` with no arguments has every flag `False`.
- Types are immutable (`frozen=True`) and hashable where used as dict keys.

**Acceptance criteria**
- [ ] `mypy --strict` clean with no `Any` in public signatures.
- [ ] `import vhecfsck.models.corpus` pulls in nothing from `core`, `adapters` or `server`.

**Guardrails:** no logic in `models/` beyond validation. No I/O. No metric computation.

---

## P1-02 — `IndexAdapter` protocol

**Depends on:** P1-01 · **Size:** L (atomic — a contract must land whole) · **Touches:** `vhecfsck/adapters/base.py`, `tests/unit/test_adapter_protocol.py`

**Goal:** the interface from [`01-architecture.md §3`](../01-architecture.md), exactly.

**Contract**
- `IndexAdapter` as a `@runtime_checkable Protocol` with the methods and properties listed
  in the architecture document. **No write methods exist** — not disabled, absent.
- `SearchParams` typed mapping with the union of documented engine knobs (`nprobe`,
  `ef_search`, `refine_factor`, `exact`), all optional, echoed back in `effective_params`.
- Shared helpers in `base.py` that adapters may reuse: L2 normalisation with tolerance
  assertion, string-ID to dense-`int64` mapping (mapping stays adapter-side and is never
  exported), batch iteration utilities.
- A module docstring stating the read-only contract in the imperative, because that
  docstring is the first thing a contributor writing a fourth adapter will read.

**Tests first**
- A minimal conforming stub satisfies `isinstance(stub, IndexAdapter)`.
- A stub missing one method does **not** satisfy it.
- `dir(IndexAdapter)` contains none of the denylisted write names from P0-09 — a test that
  makes accidental future addition of a write method fail loudly.

**Acceptance criteria**
- [ ] Protocol is complete enough that P5 (LanceDB) requires **no change** to it. If P5
      forces a change, record what was missed in [ADR-0013](../adr/0013-adapter-protocol.md)
      as an amendment rather than editing history.
- [ ] Every optional read returns `None` (not an exception) when the capability is absent.

---

## P1-03 — Synthetic corpus generator

**Depends on:** P1-01 · **Size:** M · **Touches:** `vhecfsck/synthetic/generator.py`, `tests/unit/test_generator.py`

**Goal:** reproducible corpora with realistic geometry.

**Contract**
- `generate_corpus(n, d, *, n_clusters, cluster_std, cluster_size_skew, seed, metric_space)`
  returning ids plus `float32` vectors.
- Cluster sizes follow a controllable power-law skew (`cluster_size_skew = 0.0` → uniform),
  because real embedding corpora are never balanced and a uniform corpus would make the
  partition-imbalance metric untestable.
- Cosine spaces produce L2-normalised output; `DOT` spaces support a configurable norm
  distribution, which is what makes the magnitude-driven hubness case in
  [`02-metrics-spec.md §3.6`](../02-metrics-spec.md) reachable.
- Memory-aware: generates in blocks, never materialising more than one block beyond the
  output array. Must produce 1M × 768 within the memory budget.
- Returns a `CorpusSpec` recording every parameter, so a report can state exactly what was
  generated.

**Tests first**
- Same seed → byte-identical arrays; different seed → different arrays.
- `cluster_size_skew = 0` gives cluster sizes within a few percent of uniform; high skew
  gives a dominant cluster.
- Cosine output norms are within `1e-4` of 1.
- Shapes, dtype and contiguity as declared.

**Acceptance criteria**
- [ ] 100k × 768 generates in under 5 s.
- [ ] No `float64` intermediate anywhere in the path (asserted by dtype checks).

---

## P1-04 — Injectable pathologies

**Depends on:** P1-03 · **Size:** M · **Touches:** `vhecfsck/synthetic/pathologies.py`, `tests/unit/test_pathologies.py`

**Goal:** the test oracle for the whole project. Each operator produces a corpus whose true
metric value is known analytically, which is what lets us assert that a metric is *correct*
rather than merely *stable*.

**Contract** — four operators, each seeded, each returning updated state plus a
`GroundTruthAnnotation` recording the true induced values:

| Operator | Parameters | Induces | Known true value |
| :--- | :--- | :--- | :--- |
| `apply_churn` | `delete_fraction`, `skew` (uniform → concentrated in a few clusters/fragments) | Tombstones | Exact DFI, exact per-fragment distribution |
| `inject_hubs` | `n_hubs`, `strength` | Cannibalising hubs, placed at inter-cluster centroids (and, for `DOT`, via inflated norms) | Hub IDs; `hub_share` bounded below by construction |
| `inject_antihubs` | `n_antihubs`, `distance_factor` | Isolated outliers | Anti-hub IDs; `antihub_fraction` bounded below |
| `skew_partitions` | `target_cv` or `growth_factor` | IVF imbalance, by appending vectors into a subset of existing cells without retraining — the `lance#4164` mechanism | Exact partition sizes, exact CV |

- Operators compose in any order and remain deterministic under composition.
- `GroundTruthAnnotation` is what P2's tests assert against.

**Tests first**
- `apply_churn(0.2)` yields exactly `round(0.2·n)` tombstones and an exact DFI of `0.2`.
- `inject_hubs` produces vectors that are genuinely top-10 for a disproportionate number of
  probes, verified by brute force in the test itself, not assumed.
- `skew_partitions(target_cv=1.5)` yields a measured CV within 5% of 1.5.
- Composition order changes the corpus but never the determinism.

**Acceptance criteria**
- [ ] Every operator emits a `GroundTruthAnnotation` with the true value it induced.
- [ ] Operators never mutate their input in place (pure functions returning new state).

---

## P1-05 — `SyntheticAdapter` with a real approximate-search model

**Depends on:** P1-02, P1-04 · **Size:** L · **Touches:** `vhecfsck/adapters/synthetic_adapter.py`, `tests/unit/test_synthetic_adapter.py`

**Goal:** the single most important design decision in this phase.

A synthetic adapter that always answers exactly would make canary recall a constant `1.0`,
and there would be no way to test the `WARN` and `FAIL` paths, no demo, and no evidence the
tool detects anything. The obvious fix — injecting random noise into results — is worse than
useless: it would let us claim detection of a failure mode we never actually simulated.

So the synthetic adapter implements a **simplified but mechanically faithful** IVF search
with tombstone post-filtering. Degradation emerges from the same causes as in production
engines, which means the demo reproduces the real mechanism rather than illustrating it.

**Contract**
- Three search modes:
  - `exact` — brute force. Recall is `1.0` by construction; the sanity baseline that proves
    the measurement apparatus itself is not lossy.
  - `ivf` — seeded k-means centroids fitted **once** at "index build" time, `nprobe` cells
    scanned per query. Appending vectors without refitting reproduces centroid drift and
    partition imbalance exactly as `lance#4164` describes.
  - `ivf_tombstoned` — as `ivf`, plus the critical step: gather the top `ef_budget`
    candidates by distance, **then** drop tombstoned IDs, **then** return the top `k` of the
    survivors. This is precisely the pgvector/Weaviate/Qdrant path-blocking mechanism, and
    it is what makes a query legitimately return fewer than `k` results — or none.
- Honest `Capabilities`: exact deleted counts, exact partition sizes, enumeration and random
  access all supported; `report_graph_stats` `False` (there is no graph), so the
  `UNAVAILABLE` code path gets exercised from day one instead of being discovered in P7.
- `counts()` derived from the pathology annotations, so it is exact by construction.
- Optional in-memory persistence to a `.npz` fixture, so expensive corpora are generated
  once per test session.

**Tests first**
- `exact` mode gives recall exactly `1.0` on every query — if this ever fails, the ground
  truth implementation is wrong, not the adapter.
- `ivf` mode recall decreases monotonically as `nprobe` decreases.
- `ivf_tombstoned` with a high delete fraction and a tight `ef_budget` produces genuinely
  short returns, including empty results — reproducing `pgvector#244` in miniature, in a
  unit test, with no database.
- Satisfies `isinstance(adapter, IndexAdapter)`.
- Full contract suite (P1-07) passes.

**Acceptance criteria**
- [ ] The recall collapse is reproducible and seeded: a documented `(delete_fraction,
      ef_budget, nprobe)` triple reliably produces recall below `0.70`.
- [ ] No pathology is simulated by random result corruption. Every degradation traces to a
      modelled mechanism.

**Guardrails:** the adapter may not import from `core/`. Its k-means is its own private
implementation detail, not shared with the metric that measures its partitions — sharing
code between the thing measured and the measuring instrument would make the test circular.

---

## P1-06 — Adapter registry and target URI resolution

**Depends on:** P1-05 · **Size:** S · **Touches:** `vhecfsck/adapters/registry.py`, `tests/unit/test_registry.py`

**Contract**
- Resolve a target string to an adapter: `synthetic://scenario-name`,
  `lance:///path/to/data.lance` (and a bare filesystem path with a `.lance` suffix),
  `qdrant://host:6333/collection`, `postgres://…?table=…&column=…`.
- Engine SDKs are imported lazily, inside the adapter factory, so the base install stays
  free of engine dependencies and a missing extra produces a clear message
  (`pip install "vhecfsck[qdrant]"`) rather than an `ImportError` traceback.
- Unknown scheme → `UsageError` (exit `4`) listing the supported schemes.

**Tests first**
- Every documented scheme resolves to the right adapter class without importing its SDK.
- A missing optional dependency produces the actionable install hint.
- Credentials embedded in a URI never appear in the error message (ties to P0-06).

**Acceptance criteria**
- [ ] `--target` accepts every documented form.
- [ ] Registry adds a new adapter by registration, with no `if/elif` chain to edit.

---

## P1-07 — Shared adapter contract suite

**Depends on:** P1-02, P1-05 · **Size:** L · **Touches:** `tests/contract/test_adapter_contract.py`, `tests/contract/conftest.py`

**Goal:** one parametrised suite that every present and future adapter must pass unmodified.
This is what makes adding an engine a bounded task instead of an open-ended one.

**Contract** — the suite asserts, for every adapter fixture:
- Protocol conformance and full type correctness of every return value.
- `dimension` and `metric_space` are stable across calls and match the vectors returned.
- `iter_live_vectors` yields exactly `counts().live` vectors, with unique IDs and no dead
  IDs.
- `sample_ids(n, seed)` is deterministic, returns `min(n, live)` unique live IDs.
- `fetch_vectors(ids)` returns rows in the requested order and round-trips
  `sample_ids → fetch_vectors` bit-exactly against `iter_live_vectors`.
- `search` respects `k`, pads short returns with `-1`, never returns a dead ID unless the
  adapter declares that it may, and echoes `effective_params`.
- **Capability honesty:** for every `False` capability, the corresponding method returns
  `None` — and the suite asserts the metric layer will therefore report `UNAVAILABLE`.
  Unsupported capabilities are *tested*, not skipped.
- **Read-only behaviour:** a full audit-shaped read sequence leaves the target's observable
  state unchanged (counts identical before and after; for file-backed adapters, content
  hashes and mtimes identical — extended in P5).
- `close()` is idempotent and the adapter raises a clear error if used after close.

**Acceptance criteria**
- [ ] Passes for `SyntheticAdapter` with zero skips.
- [ ] Adding a new adapter requires only registering a fixture, not editing the suite.
- [ ] The suite is documented in `CONTRIBUTING.md` as the definition of "a working adapter".

---

## P1-08 — Named scenarios

**Depends on:** P1-04, P1-05 · **Size:** M · **Touches:** `vhecfsck/synthetic/scenarios.py`, `tests/unit/test_scenarios.py`

**Goal:** fixed, seeded scenarios that pin every downstream exit-code test and drive the
demo. Without these, the CLI's exit-code tests would each have to hand-assemble a corpus,
and the demo's behaviour would drift as parameters were tuned.

| Scenario | Composition | Expected verdict |
| :--- | :--- | :--- |
| `healthy` | Balanced clusters, no churn, generous `nprobe` | `OK` (exit `0`) |
| `drifted` | 10× growth into existing cells without refitting — `lance#4164` | `WARN` (exit `1`) |
| `tombstoned` | 35% skewed churn with a tight `ef_budget` — `pgvector#244` | `FAIL` (exit `2`) |
| `hubby` | High dimensionality, injected hubs and isolated outliers | `FAIL` on hubness metrics |
| `capability_limited` | Adapter with `report_deleted_counts = False` | `INCONCLUSIVE` (exit `3`) |
| `tiny` | 50 vectors, below every guard | `UNAVAILABLE` metrics, exit `3` |

**Contract**
- Each scenario is a pure function returning a configured `SyntheticAdapter` plus the
  expected verdict and expected per-metric states.
- Small by default (~20k vectors) so the whole set runs in CI in seconds; a `--size large`
  variant exists for perf work.
- Scenario definitions are frozen once P3's exit-code tests depend on them. Changing one is
  a deliberate act with a changelog entry, not an incidental tuning tweak.

**Acceptance criteria**
- [ ] Each scenario deterministically produces its documented verdict (asserted in P3).
- [ ] The full set builds in under 20 s on CI hardware.
- [ ] Each scenario carries a one-line docstring naming the real-world issue it mimics.

---

## Phase exit checklist

- [ ] Contract suite green against `SyntheticAdapter`, zero skips.
- [ ] Every pathology operator emits a machine-checkable true value.
- [ ] `ivf_tombstoned` reproduces an empty result set for a query that has live neighbours —
      the core failure mode, demonstrated in a unit test.
- [ ] `make verify` green; coverage ≥90% on `synthetic/` and `adapters/`.
- [ ] Nothing in `synthetic/` or `adapters/` imports `core/` (import-linter enforced).
