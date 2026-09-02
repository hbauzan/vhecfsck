# P7 — Qdrant and pgvector Adapters

**Goal:** prove the adapter protocol generalises beyond a file-based engine, and reproduce
[`qdrant#7147`](https://github.com/qdrant/qdrant/issues/7147) and
[`pgvector#244`](https://github.com/pgvector/pgvector/issues/244) as automated tests.

These two engines are harder than LanceDB in ways that matter. Both are servers, so CI needs
containers. Both are HNSW-based, so the tombstone mechanism is graph path blocking rather than
partition imbalance. And both expose statistics that are easy to misread — the single biggest
correctness risk in this phase is confidently reporting a number that means something other
than what we think it means.

**Entry criteria:** P5 complete. The adapter protocol has survived one real engine.

**Exit gate**

```bash
pytest tests/integration -q                 # full matrix: synthetic, lancedb, qdrant, pgvector
pytest tests/integration -k repro -q        # all three reproduction scenarios
```

---

## P7-01 — Container-based integration harness

**Depends on:** P0-10 · **Size:** M · **Touches:** `tests/integration/conftest.py`, `.github/workflows/ci.yml`

**Contract**
- `testcontainers` fixtures for Qdrant and PostgreSQL+pgvector, session-scoped, with pinned
  image tags and health-gated startup.
- Local runs skip with an actionable message when Docker is unavailable; CI treats a skip as a
  failure, so nobody merges an accidentally-skipped suite.
- Image layers cached in CI; total added wall time under four minutes.
- A seeding helper that builds a collection/table with a given corpus, index configuration and
  churn pattern, shared by both engines' tests so scenarios stay comparable across engines.

**Tests first**
- Both containers start, are reachable, and are torn down cleanly.
- Seeding is deterministic under a fixed seed.
- Port collisions and slow starts are handled by the harness, not by a `sleep`.

---

## P7-02 — Qdrant adapter: descriptor, counts and the telemetry trap

**Depends on:** P1-02, P7-01 · **Size:** L · **Touches:** `vhecfsck/adapters/qdrant_adapter.py`, `tests/integration/test_qdrant_counts.py`

**Goal:** get DFI right, or report nothing. This ticket is where
[`02-metrics-spec.md §4.2`](../../02-metrics-spec.md) has to be honoured under pressure.

**Contract**
- Read collection info for dimension, distance metric and HNSW configuration.
- **DFI comes from per-segment deleted-vector counts.** The convenient alternative —
  `points_count` versus `indexed_vectors_count` — is wrong, because `indexed_vectors_count`
  also excludes vectors in segments below the indexing threshold. On a freshly loaded, clean
  collection that ratio reports fragmentation that does not exist. If segment-level counts are
  not obtainable from the pinned version, DFI is `UNAVAILABLE`. Do not substitute the number
  that happens to be available for the number that is correct.
- Enumeration via the scroll API with pagination and vectors included; random access via the
  points retrieve endpoint.
- Search via the query/search API with `hnsw_ef` honoured and echoed as effective params.
- gRPC preferred when available for enumeration throughput, with HTTP as the fallback; the
  transport used is recorded in the report.
- Read-only: only `GET` and read-shaped `POST` endpoints (`/points/scroll`, `/points/search`).
  A denylist test asserts no mutating endpoint appears anywhere in the module.

**Tests first**
- Descriptor correct for cosine, dot and euclid collections.
- A clean, freshly loaded collection reports DFI `0.0` (or `UNAVAILABLE`) — **never** a
  spurious non-zero value. This is the regression test for the trap above and the most
  important assertion in the ticket.
- A collection with known deletions before optimisation reports the exact deleted count.
- Contract suite green.
- Read-only: collection counts and segment state unchanged after a full audit.

---

## P7-03 — Reproduce `qdrant#7147` (multitenant subgraph corruption)

**Depends on:** P7-02 · **Size:** L · **Touches:** `tests/integration/test_repro_qdrant_7147.py`, `docs/scenarios/qdrant-7147.md`

**Goal:** the most compelling scenario in the project — precision falling from 0.98 to 0.61
while every health check stays green.

**Contract**
- Seed a multitenant collection with a tenant-keyed payload index (`is_tenant: true`), many
  tenants, then drive the churn and segment consolidation the issue describes.
- Assert the pathology independently of our tooling first: per-tenant filtered search
  precision measurably drops while `/healthz` and collection status remain green. If the
  pathology cannot be reproduced on the pinned version — because it has been fixed — say so
  in the docs and keep the test as a guard against regression, rather than quietly weakening
  the assertion until it passes.
- Assert `vhecfsck` detects it and exits non-zero.
- **This requires per-tenant (filtered) canary recall**, which the MVP does not have. Add
  `filtered_search` to `Capabilities` and a `--filter` / `--group-by` option to the canary
  metric, reported as a per-group breakdown. An aggregate recall averaged across tenants can
  hide a catastrophic failure in one tenant — which is precisely the shape of this issue, and
  precisely why the aggregate-only version of the metric would have missed it.
- Document the scenario with measured numbers and the upstream link.

**Tests first** — the assertions above, plus: an aggregate-only audit **fails** to flag the
issue while the grouped audit catches it. That contrast is the argument for the feature, and
it belongs in a test so it cannot be lost.

**Acceptance criteria**
- [ ] Per-tenant recall breakdown appears in the report under an additive schema change
      (minor `schema_version` bump).
- [ ] Deterministic over ten runs, or explicitly documented as probabilistic with a measured
      reproduction rate. A flaky test that is honest about being flaky is acceptable here; a
      flaky test presented as deterministic is not.

---

## P7-04 — pgvector adapter: read-only session and catalog introspection

**Depends on:** P1-02, P7-01 · **Size:** L · **Touches:** `vhecfsck/adapters/pgvector_adapter.py`, `tests/integration/test_pgvector.py`

**Contract**
- Connect with `default_transaction_read_only = on` **and** inside an explicitly read-only
  transaction, so a write is rejected by the server rather than merely absent from our code.
  Defence in depth matters more here than anywhere else in the project: this is someone's
  production PostgreSQL.
- Document and recommend a dedicated `SELECT`-only role in the engine guide, and warn (once)
  when connected as a superuser.
- Introspect via the catalog: index kind (`hnsw` / `ivfflat`), operator class (which
  determines the metric space — `vector_l2_ops`, `vector_cosine_ops`, `vector_ip_ops`),
  dimension from the column type modifier, and index build parameters (`m`, `ef_construction`,
  `lists`).
- Counts: `n_live_tup` / `n_dead_tup` from `pg_stat_user_tables`, plus `pgstattuple` when the
  extension and privileges allow. Both are flagged `proxy = true` and `estimated = true`:
  they are table-level statistics refreshed by the stats collector, not index-level tombstone
  counts, and `evidence_strength` is capped at `medium` accordingly.
- Enumeration with a server-side cursor and a bounded fetch size — never `SELECT *` into
  memory against a production table.
- Search with `hnsw.ef_search` / `ivfflat.probes` set per-transaction via `SET LOCAL`, and the
  effective value echoed. Also record whether the server supports iterative scans (the v0.8.0
  mitigation), because it materially changes how a recall number should be read.
- Confirm via `EXPLAIN` that the query plan actually uses the index. A sequential scan would
  yield a perfect recall of `1.0` and a completely meaningless audit — silently measuring the
  wrong thing. If the planner refuses the index, report `UNAVAILABLE` with that reason.

**Tests first**
- A write attempt on the audit connection is rejected by the server.
- Metric space derived correctly from each operator class.
- `EXPLAIN` guard: a table small enough that the planner prefers a sequential scan yields
  `UNAVAILABLE(index_not_used)`, not a recall of `1.0`.
- DFI flagged `proxy` and `estimated`, evidence capped at `medium`.
- Contract suite green.

---

## P7-05 — Reproduce `pgvector#244` (dead tuples collapse recall)

**Depends on:** P7-04 · **Size:** M · **Touches:** `tests/integration/test_repro_pgvector_244.py`, `docs/scenarios/pgvector-244.md`

**Contract**
- Seed a table with an HNSW index, then perform heavy `UPDATE`/`DELETE` churn with autovacuum
  disabled for the table.
- Assert the pathology independently: recall collapses (toward zero in the extreme case) and
  queries return short or empty result sets, while the table, the index and the server all
  look healthy.
- Assert `vhecfsck` detects it: canary recall `FAIL`, `detail.returned_invalid` and
  `short_returns` non-zero, DFI elevated, exit `2`.
- Assert the counterfactual: after `VACUUM`, metrics recover. `vhecfsck` never runs the
  `VACUUM` itself — the test harness does, explicitly, as an operator action. The read-only
  invariant is not suspended for convenience in tests, because a test helper is exactly how
  a write path gets introduced by accident later.
- Record whether iterative scans change the outcome on the pinned version.

**Acceptance criteria**
- [ ] `returned_invalid` is the smoking gun in the report, not just a low recall number. That
      field is what tells an operator *why*, and it is the strongest single piece of evidence
      the tool produces.
- [ ] Documented with measured before/after numbers.

---

## P7-06 — HNSW graph statistics (best effort)

**Depends on:** P7-02, P7-04 · **Size:** M · **Touches:** both adapters, `vhecfsck/core/partitions.py`, `vhecfsck/core/fragmentation.py`

**Contract**
- Where an engine exposes it, populate `GraphStats`: in-degree histogram, entry points, and
  `entrypoint_tombstoned` — the boolean behind the Weaviate startup pathology and the most
  actionable single bit in the whole tool.
- Enable the `entrypoint_tombstoned` escalation path already implemented in P2-07.
- Report the unreachable-node fraction if derivable without writing or an expensive full
  traversal.
- Where unavailable — likely for both engines at their pinned versions — `UNAVAILABLE` with a
  precise reason. This ticket is explicitly allowed to conclude "not obtainable", provided the
  finding is documented in the engine guides. A negative result recorded is worth more than an
  approximation invented.

**Acceptance criteria**
- [ ] Either real graph statistics, or a documented explanation of why not, per engine.
- [ ] No metric is fabricated from an unrelated proxy.

---

## P7-07 — Cross-engine consistency suite

**Depends on:** P7-02, P7-04, P5 · **Size:** M · **Touches:** `tests/integration/test_cross_engine.py`

**Goal:** the same corpus, the same pathology, three engines — do the metrics agree?

**Contract**
- Seed one identical corpus (same seed, same vectors, same deletions) into the synthetic
  adapter, LanceDB, Qdrant and pgvector, configured for equivalent search effort.
- Assert that intrinsic metrics — hub share, anti-hub fraction — agree within a tight
  tolerance across all four, since they are properties of the embedding space and must not
  depend on the engine. A disagreement is a bug in an adapter's enumeration or normalisation,
  and this test is the only place that would catch it.
- Assert engine-dependent metrics (recall, DFI) fall in a plausible, documented range rather
  than an exact value.
- Record the comparison table in the docs — it is genuinely interesting content and doubles as
  evidence the tool is measuring the space rather than the plumbing.

**Acceptance criteria**
- [ ] Hub share and anti-hub fraction agree within 2% across engines, or the discrepancy is
      explained and traced to a specific cause.
- [ ] The table is regenerable with one command.

---

## P7-08 — Engine guides and capability matrix

**Depends on:** P7-02, P7-04, P7-06 · **Size:** M · **Touches:** `docs/engines/qdrant.md`, `docs/engines/pgvector.md`, `docs/engines/capability-matrix.md`, `README.md`

**Contract**
- Per engine: quickstart, required privileges, recommended read-only role setup, tested
  version range, and the exact provenance of every metric (exact / proxy / unavailable, with
  the reason).
- One consolidated capability matrix: engines × metrics, showing exactness. This is the table
  a prospective user reads before installing, and its honesty is the product's credibility.
- The pgvector guide must state plainly that DFI is a table-level proxy, and the Qdrant guide
  must state why the convenient `indexed_vectors_count` ratio is not used.

---

## Phase exit checklist

- [x] Contract suite green for all four adapters, zero skips, in CI.
- [x] Both reproductions automated, with measured numbers in the docs and counterfactual
      recovery asserted.
- [x] Per-tenant / filtered recall breakdown implemented (an additive schema change).
- [x] pgvector audits run in a server-enforced read-only transaction, with an `EXPLAIN` guard
      against silently measuring a sequential scan.
- [x] Qdrant DFI is exact or `UNAVAILABLE` — never the misleading proxy.
- [x] Cross-engine intrinsic metrics agree, or the discrepancy is explained.
- [x] Capability matrix published.
