"""P2-05: canary recall — Fixture A, edge cases, self-exclusion, bootstrap.

Tests fail before ``vhecfsck.core.canary`` exists (RED), then lock the
``02-metrics-spec.md`` §2 contract.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from vhecfsck.core.canary import (
    CANARY_METRIC_ID,
    CANARY_RTOL,
    compute_canary_recall,
    score_query_recall,
)
from vhecfsck.models import (
    EvidenceStrength,
    MetricSpace,
    MetricState,
    VectorBatch,
)


def _fixture_a_corpus() -> tuple[np.ndarray, np.ndarray]:
    corpus = np.asarray(
        [[0, 0], [1, 0], [0, 1], [10, 0], [10, 1], [0, 10]],
        dtype=np.float32,
    )
    query = np.asarray([[0.1, 0.1]], dtype=np.float32)
    return corpus, query


def test_fixture_a_recall_id_half_recall_dist_one() -> None:
    """Fixture A — §2.6 / CORRECTION 2: must never be deleted."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 2]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={"exact": True},
        bootstrap_seed=1337,
        enforce_min_queries=False,
        bootstrap_resamples=50,
    )
    assert result.id == CANARY_METRIC_ID
    assert result.detail["recall_id"] == 0.5
    assert result.detail["recall_dist"] == 1.0
    assert result.value == 1.0  # gates on recall_dist
    assert result.state is MetricState.OK


def test_score_query_recall_fixture_a_directly() -> None:
    """Per-query scorer matches Fixture A numbers exactly."""
    d_k = math.sqrt((1.0 - 0.1) ** 2 + (0.0 - 0.1) ** 2)
    # true dist to id2 == d_k (tie).
    dist0 = math.sqrt((0.0 - 0.1) ** 2 + (0.0 - 0.1) ** 2)
    dist2 = math.sqrt((0.0 - 0.1) ** 2 + (1.0 - 0.1) ** 2)
    rid, rdist, diag = score_query_recall(
        gt_ids=[0, 1],
        returned_ids=[0, 2],
        returned_true_distances=[dist0, dist2],
        d_k=d_k,
        n_eff=2,
        rtol=CANARY_RTOL,
    )
    assert rid == 0.5
    assert rdist == 1.0
    assert diag.boundary_tie is True


def test_exact_search_adapter_recall_is_one() -> None:
    """Exact-mode SyntheticAdapter → recall_dist == 1.0."""
    from numpy.random import default_rng
    from vhecfsck.adapters import SyntheticAdapter
    from vhecfsck.models import MetricSpace
    from vhecfsck.synthetic import corpus_state_from_generated, generate_corpus

    gen = generate_corpus(
        200,
        16,
        n_clusters=4,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=42,
        metric_space=MetricSpace.L2,
    )
    adapter = SyntheticAdapter(corpus_state_from_generated(gen), mode="exact")
    try:
        # External (non-corpus) queries — exact search must hit recall 1.0.
        rng = default_rng(7)
        queries = np.ascontiguousarray(
            rng.standard_normal((40, adapter.dimension), dtype=np.float32)
        )
        live = list(adapter.iter_live_vectors(batch_size=512))
        all_ids = np.concatenate([b.ids for b in live])
        all_vecs = np.concatenate([b.vectors for b in live], axis=0)
        result = compute_canary_recall(
            corpus_ids=all_ids,
            corpus_vectors=all_vecs,
            queries=queries,
            returned_ids=adapter.search(queries, 10, params={"exact": True}).ids,
            metric_space=adapter.metric_space,
            k=10,
            self_exclude=False,
            query_source="synthetic",
            search_params={"exact": True},
            bootstrap_seed=99,
            bootstrap_resamples=100,
        )
        assert result.state is not MetricState.UNAVAILABLE
        assert result.detail["recall_dist"] == pytest.approx(1.0)
        assert result.detail["recall_id"] == pytest.approx(1.0)
        assert result.value == pytest.approx(1.0)
    finally:
        adapter.close()


def test_edge_n_live_zero_unavailable() -> None:
    """§2.5 case 1: n_live == 0 → UNAVAILABLE."""
    result = compute_canary_recall(
        corpus_ids=np.asarray([], dtype=np.int64),
        corpus_vectors=np.zeros((0, 2), dtype=np.float32),
        queries=np.asarray([[0.1, 0.1]], dtype=np.float32),
        returned_ids=np.asarray([[-1, -1]], dtype=np.int64),
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        enforce_min_queries=False,
    )
    assert result.state is MetricState.UNAVAILABLE
    assert result.value is None
    assert result.unavailable_reason is not None
    assert "n_live" in result.unavailable_reason or "empty" in result.unavailable_reason


def test_edge_n_live_less_than_k_normalises_by_n_live() -> None:
    """§2.5 case 1: n_live < K → denominator is n_live."""
    corpus = np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    ids = np.asarray([0, 1], dtype=np.int64)
    query = np.asarray([[0.1, 0.0]], dtype=np.float32)
    returned = np.asarray([[0, 1, -1, -1]], dtype=np.int64)  # k=4 slots
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=4,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=100,
        enforce_min_queries=False,
    )
    assert result.state is not MetricState.UNAVAILABLE
    assert result.detail["recall_dist"] == pytest.approx(1.0)
    assert result.detail["recall_id"] == pytest.approx(1.0)


def test_edge_short_returns() -> None:
    """§2.5 case 2: fewer than K results → misses + short_returns."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    # Only one neighbour returned; second slot padded.
    returned = np.asarray([[0, -1]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=100,
        enforce_min_queries=False,
    )
    assert result.detail["short_returns"] >= 1
    assert result.detail["recall_id"] == pytest.approx(0.5)
    assert result.detail["recall_dist"] == pytest.approx(0.5)


def test_edge_duplicate_returns() -> None:
    """§2.5 case 3: duplicate IDs deduped; duplicate_returns tallied."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 0]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=100,
        enforce_min_queries=False,
    )
    assert result.detail["duplicate_returns"] >= 1
    assert result.detail["recall_id"] == pytest.approx(0.5)


def test_edge_dead_unknown_ids() -> None:
    """§2.5 case 4: dead/unknown IDs → miss + returned_invalid."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 999]], dtype=np.int64)  # 999 unknown
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=100,
        enforce_min_queries=False,
    )
    assert result.detail["returned_invalid"] >= 1
    assert result.detail["recall_id"] == pytest.approx(0.5)
    assert result.detail["recall_dist"] == pytest.approx(0.5)


def test_edge_boundary_ties_recorded() -> None:
    """§2.5 case 5: Fixture A style tie increments boundary_ties."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 2]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=100,
        enforce_min_queries=False,
    )
    assert result.detail["boundary_ties"] >= 1


def test_edge_duplicate_vectors_legal_deterministic() -> None:
    """§2.5 case 6: exact duplicate vectors — ID tie-break, no crash."""
    corpus = np.asarray([[0.0, 0.0], [0.0, 0.0], [5.0, 0.0]], dtype=np.float32)
    ids = np.asarray([0, 1, 2], dtype=np.int64)
    query = np.asarray([[0.1, 0.0]], dtype=np.float32)
    # GT for k=1 is id 0 (ascending id among equidistant 0 and 1).
    returned = np.asarray([[1]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=1,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.detail["recall_id"] == pytest.approx(0.0)
    assert result.detail["recall_dist"] == pytest.approx(1.0)


def test_edge_mid_audit_id_disappearance() -> None:
    """§2.5 case 7: IDs vanish mid-audit → snapshot_inconsistent, no crash."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    # Engine returns id that was live at snapshot start but absent from corpus map.
    returned = np.asarray([[0, 42]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        live_ids_at_start=frozenset({0, 1, 2, 3, 4, 5, 42}),
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.detail["snapshot_inconsistent"] is True
    assert result.detail["returned_invalid"] >= 1
    assert result.state is not MetricState.UNAVAILABLE or result.unavailable_reason


def test_edge_query_same_vector_different_id_not_self_excluded() -> None:
    """§2.5 case 8: same coords, different ID — legitimate neighbour, keep it."""
    corpus = np.asarray([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    ids = np.asarray([10, 11, 12], dtype=np.int64)
    # Query drawn from id 10; id 12 has identical coords — must remain eligible.
    query = np.asarray([[0.0, 0.0]], dtype=np.float32)
    source = np.asarray([10], dtype=np.int64)
    returned = np.asarray([[12, 11]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        query_source_ids=source,
        self_exclude=True,
        query_source="corpus",
        search_params={},
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    # GT excluding 10: [12, 11] (12 at dist 0). Engine returns both → perfect.
    assert result.detail["recall_id"] == pytest.approx(1.0)
    assert result.detail["recall_dist"] == pytest.approx(1.0)


def test_edge_search_params_echoed() -> None:
    """§2.5 case 9: effective search params land in sampling."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 1]], dtype=np.int64)
    params = {"nprobe": 20, "ef_search": 64}
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params=params,
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.sampling["search_params"]["nprobe"] == 20
    assert result.sampling["search_params"]["ef_search"] == 64


def test_edge_truncated_ground_truth() -> None:
    """§2.5 case 10: truncated GT → detail.truncated, never silent partial."""
    corpus = np.asarray([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]], dtype=np.float32)
    ids = np.asarray([0, 1, 2], dtype=np.int64)
    query = np.asarray([[0.1, 0.0]], dtype=np.float32)
    returned = np.asarray([[0, 1]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        ground_truth_truncated=True,
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.detail["truncated"] is True
    assert result.evidence_strength is EvidenceStrength.LOW


def test_q_less_than_five_unavailable() -> None:
    """§2.4 guard: Q < 5 → UNAVAILABLE."""
    corpus = np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    ids = np.asarray([0, 1], dtype=np.int64)
    queries = np.asarray(
        [[0.1, 0.0], [0.2, 0.0], [0.3, 0.0], [0.4, 0.0]],
        dtype=np.float32,
    )
    returned = np.asarray([[0, 1]] * 4, dtype=np.int64)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=queries,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
    )
    assert result.state is MetricState.UNAVAILABLE
    assert "Q" in (result.unavailable_reason or "") or "queries" in (
        result.unavailable_reason or ""
    )


def test_self_exclusion_changes_result_by_approx_one_over_k() -> None:
    """Corpus-drawn queries: excluding self moves mean recall by ~1/k."""
    from vhecfsck.adapters import SyntheticAdapter
    from vhecfsck.models import MetricSpace
    from vhecfsck.synthetic import corpus_state_from_generated, generate_corpus

    k = 10
    gen = generate_corpus(
        300,
        16,
        n_clusters=4,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=11,
        metric_space=MetricSpace.L2,
    )
    adapter = SyntheticAdapter(corpus_state_from_generated(gen), mode="exact")
    try:
        q_ids = adapter.sample_ids(50, seed=3)
        batch = adapter.fetch_vectors(q_ids)
        live = list(adapter.iter_live_vectors(batch_size=512))
        all_ids = np.concatenate([b.ids for b in live])
        all_vecs = np.concatenate([b.vectors for b in live], axis=0)
        search = adapter.search(batch.vectors, k, params={"exact": True}).ids
        common = {
            "corpus_ids": all_ids,
            "corpus_vectors": all_vecs,
            "queries": batch.vectors,
            "returned_ids": search,
            "metric_space": adapter.metric_space,
            "k": k,
            "query_source_ids": q_ids,
            "query_source": "corpus",
            "search_params": {"exact": True},
            "bootstrap_resamples": 200,
            "bootstrap_seed": 1,
        }
        with_self = compute_canary_recall(**common, self_exclude=False)
        without = compute_canary_recall(**common, self_exclude=True)
        # Exact search recovers everything; with self included recall≈1,
        # without self the "free" hit is removed from both GT and returns
        # scoring — the inflation of *not* excluding is ~1/k on recall_id
        # when the engine also returns self (exact mode does).
        rid_with = float(with_self.detail["recall_id"])
        rid_without = float(without.detail["recall_id"])
        delta = rid_with - rid_without
        assert delta == pytest.approx(1.0 / k, abs=0.05)
    finally:
        adapter.close()


def test_tombstoned_scenario_returned_invalid_nonzero() -> None:
    """Acceptance: tombstoned scenario → detail.returned_invalid > 0.

    SyntheticAdapter filters tombstones correctly (short lists under tight
    ef_budget). The smoking-gun diagnostic is exercised with a deleted ID
    from that scenario spliced into the return set — the shape a buggy
    engine exhibits when path-blocking leaks dead IDs.
    """
    from vhecfsck.adapters import open_scenario

    opened = open_scenario("tombstoned", size="small")
    adapter = opened.adapter
    try:
        q_ids = adapter.sample_ids(40, seed=5)
        batch = adapter.fetch_vectors(q_ids)
        live_batches = list(adapter.iter_live_vectors(batch_size=1024))
        all_ids = np.concatenate([b.ids for b in live_batches])
        all_vecs = np.concatenate([b.vectors for b in live_batches], axis=0)
        search = adapter.search(
            batch.vectors,
            10,
            params={"nprobe": 1, "ef_search": 8},
        )
        deleted_probe = _first_deleted_id(adapter)
        assert deleted_probe is not None
        patched = np.array(search.ids, copy=True)
        patched[0, 0] = deleted_probe
        result = compute_canary_recall(
            corpus_ids=all_ids,
            corpus_vectors=all_vecs,
            queries=batch.vectors,
            returned_ids=patched,
            metric_space=adapter.metric_space,
            k=10,
            query_source_ids=q_ids,
            self_exclude=True,
            query_source="corpus",
            search_params=dict(search.effective_params),
            bootstrap_resamples=100,
            bootstrap_seed=5,
            live_ids_at_start=frozenset({deleted_probe})
            | frozenset(int(x) for x in all_ids),
        )
        assert result.detail["returned_invalid"] > 0
    finally:
        adapter.close()


def _first_deleted_id(adapter: object) -> int | None:
    """Locate one tombstoned id from SyntheticAdapter private state."""
    deleted = getattr(adapter, "_deleted", None)
    ids = getattr(adapter, "_ids", None)
    if deleted is None or ids is None:
        return None
    for i in range(int(ids.shape[0])):
        if bool(deleted[i]):
            return int(ids[i])
    return None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.85, MetricState.OK),
        (0.849999, MetricState.WARN),
        (0.70, MetricState.WARN),
        (0.699999, MetricState.FAIL),
    ],
)
def test_threshold_boundaries(value: float, expected: MetricState) -> None:
    """Acceptance: crossings at 0.85 / 0.70 from both sides (§2 thresholds)."""
    from vhecfsck.core.canary import state_from_recall_dist

    assert state_from_recall_dist(value, warn=0.85, fail=0.70) is expected


def test_bootstrap_ci_contains_estimate_and_is_reproducible() -> None:
    """Bootstrap 95% CI contains the point estimate; fixed seed → identical."""
    corpus, query = _fixture_a_corpus()
    # Repeat the fixture query to get Q >= 5.
    queries = np.repeat(query, 10, axis=0)
    returned = np.tile(np.asarray([[0, 2]], dtype=np.int64), (10, 1))
    ids = np.arange(6, dtype=np.int64)
    kwargs = {
        "corpus_ids": ids,
        "corpus_vectors": corpus,
        "queries": queries,
        "returned_ids": returned,
        "metric_space": MetricSpace.L2,
        "k": 2,
        "self_exclude": False,
        "query_source": "synthetic",
        "search_params": {},
        "bootstrap_resamples": 500,
        "bootstrap_seed": 42,
    }
    a = compute_canary_recall(**kwargs)
    b = compute_canary_recall(**kwargs)
    ci = a.detail["ci95"]
    assert len(ci) == 2
    assert ci[0] <= a.value <= ci[1]
    assert a.detail["ci95"] == b.detail["ci95"]
    assert a.value == b.value


def test_true_distances_recomputed_not_from_engine() -> None:
    """Engine distance field is ignored; corpus recompute decides recall_dist."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    returned = np.asarray([[0, 2]], dtype=np.int64)
    # Lies: claim id2 is infinitely far — must still score as a distance hit.
    engine_distances = np.asarray([[0.0, 1e9]], dtype=np.float32)
    result = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        engine_distances=engine_distances,
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.detail["recall_dist"] == 1.0


def test_vector_batch_corpus_path() -> None:
    """Accept a VectorBatch iterable the same way ground_truth does."""
    corpus, query = _fixture_a_corpus()
    ids = np.arange(6, dtype=np.int64)
    batches = [VectorBatch(ids=ids, vectors=corpus)]
    returned = np.asarray([[0, 2]], dtype=np.int64)
    result = compute_canary_recall(
        corpus_batches=batches,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=50,
        enforce_min_queries=False,
    )
    assert result.detail["recall_id"] == 0.5
    assert result.detail["recall_dist"] == 1.0
