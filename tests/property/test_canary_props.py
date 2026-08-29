"""Property tests for canary recall (P2-05).

Bounds, row-permutation invariance, and nprobe monotonicity on synthetic IVF.
"""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.adapters import SyntheticAdapter
from vhecfsck.core.canary import compute_canary_recall
from vhecfsck.models import MetricSpace, MetricState
from vhecfsck.synthetic import corpus_state_from_generated, generate_corpus


def _state(n: int, d: int, n_clusters: int, seed: int) -> object:
    gen = generate_corpus(
        n,
        d,
        n_clusters=n_clusters,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    return corpus_state_from_generated(gen)


def _live_matrix(adapter: SyntheticAdapter) -> tuple[np.ndarray, np.ndarray]:
    batches = list(adapter.iter_live_vectors(batch_size=1024))
    ids = np.concatenate([b.ids for b in batches])
    vecs = np.concatenate([b.vectors for b in batches], axis=0)
    return ids, vecs


def test_recall_bounds_zero_to_one() -> None:
    adapter = SyntheticAdapter(_state(120, 8, 3, 21), mode="exact")  # type: ignore[arg-type]
    try:
        q_ids = adapter.sample_ids(30, seed=2)
        batch = adapter.fetch_vectors(q_ids)
        ids, vecs = _live_matrix(adapter)
        result = compute_canary_recall(
            corpus_ids=ids,
            corpus_vectors=vecs,
            queries=batch.vectors,
            returned_ids=adapter.search(batch.vectors, 5, params={}).ids,
            metric_space=adapter.metric_space,
            k=5,
            query_source_ids=q_ids,
            self_exclude=True,
            query_source="corpus",
            search_params={},
            bootstrap_resamples=100,
        )
        assert result.state is not MetricState.UNAVAILABLE
        assert 0.0 <= float(result.detail["recall_id"]) <= 1.0
        assert 0.0 <= float(result.detail["recall_dist"]) <= 1.0
        assert 0.0 <= float(result.value) <= 1.0
    finally:
        adapter.close()


def test_permuting_corpus_rows_does_not_change_recall() -> None:
    corpus = np.asarray(
        [[0, 0], [1, 0], [0, 1], [10, 0], [10, 1], [0, 10]],
        dtype=np.float32,
    )
    ids = np.arange(6, dtype=np.int64)
    query = np.asarray([[0.1, 0.1]], dtype=np.float32)
    returned = np.asarray([[0, 2]], dtype=np.int64)
    base = compute_canary_recall(
        corpus_ids=ids,
        corpus_vectors=corpus,
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=50,
        bootstrap_seed=7,
        enforce_min_queries=False,
    )
    order = np.asarray([5, 3, 1, 0, 4, 2], dtype=np.int64)
    perm = compute_canary_recall(
        corpus_ids=ids[order],
        corpus_vectors=corpus[order],
        queries=query,
        returned_ids=returned,
        metric_space=MetricSpace.L2,
        k=2,
        self_exclude=False,
        query_source="synthetic",
        search_params={},
        bootstrap_resamples=50,
        bootstrap_seed=7,
        enforce_min_queries=False,
    )
    assert base.detail["recall_id"] == perm.detail["recall_id"]
    assert base.detail["recall_dist"] == perm.detail["recall_dist"]
    assert base.value == perm.value


@pytest.mark.slow
def test_recall_monotone_nondecreasing_in_nprobe_ivf() -> None:
    """Higher nprobe must not lower recall_dist on synthetic IVF."""
    adapter = SyntheticAdapter(
        _state(800, 16, 8, 77),  # type: ignore[arg-type]
        mode="ivf",
        n_lists=8,
        build_seed=77,
    )
    try:
        q_ids = adapter.sample_ids(40, seed=9)
        batch = adapter.fetch_vectors(q_ids)
        ids, vecs = _live_matrix(adapter)
        recalls: list[float] = []
        for nprobe in (1, 2, 4, 8):
            search = adapter.search(batch.vectors, 10, params={"nprobe": nprobe})
            result = compute_canary_recall(
                corpus_ids=ids,
                corpus_vectors=vecs,
                queries=batch.vectors,
                returned_ids=search.ids,
                metric_space=adapter.metric_space,
                k=10,
                query_source_ids=q_ids,
                self_exclude=True,
                query_source="corpus",
                search_params={"nprobe": nprobe},
                bootstrap_resamples=100,
                bootstrap_seed=9,
            )
            recalls.append(float(result.detail["recall_dist"]))
        for i in range(1, len(recalls)):
            assert recalls[i] >= recalls[i - 1] - 1e-9
    finally:
        adapter.close()


def test_recall_monotone_nprobe_smoke_small() -> None:
    """Default-suite smoke: small IVF, three nprobe steps, weak monotonicity."""
    adapter = SyntheticAdapter(
        _state(200, 8, 4, 88),  # type: ignore[arg-type]
        mode="ivf",
        n_lists=4,
        build_seed=88,
    )
    try:
        q_ids = adapter.sample_ids(30, seed=1)
        batch = adapter.fetch_vectors(q_ids)
        ids, vecs = _live_matrix(adapter)
        r1 = compute_canary_recall(
            corpus_ids=ids,
            corpus_vectors=vecs,
            queries=batch.vectors,
            returned_ids=adapter.search(batch.vectors, 5, params={"nprobe": 1}).ids,
            metric_space=adapter.metric_space,
            k=5,
            query_source_ids=q_ids,
            self_exclude=True,
            query_source="corpus",
            search_params={"nprobe": 1},
            bootstrap_resamples=50,
        )
        r4 = compute_canary_recall(
            corpus_ids=ids,
            corpus_vectors=vecs,
            queries=batch.vectors,
            returned_ids=adapter.search(batch.vectors, 5, params={"nprobe": 4}).ids,
            metric_space=adapter.metric_space,
            k=5,
            query_source_ids=q_ids,
            self_exclude=True,
            query_source="corpus",
            search_params={"nprobe": 4},
            bootstrap_resamples=50,
        )
        assert float(r4.detail["recall_dist"]) >= float(r1.detail["recall_dist"]) - 1e-9
    finally:
        adapter.close()
