"""P2-03: hand-verified fixtures A/B/C against the naive oracle.

These numbers were computed before being written into ``02-metrics-spec.md``.
They must never be deleted or "modernised".
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from vhecfsck.models import MetricSpace

from tests.oracle.reference import naive_cv, naive_knn, naive_nk, naive_recall


def test_fixture_a_naive_knn_and_recall() -> None:
    """Fixture A — §2.6: L2, K=2, tie at boundary → recall_id 0.5, recall_dist 1.0."""
    corpus = np.asarray(
        [[0, 0], [1, 0], [0, 1], [10, 0], [10, 1], [0, 10]],
        dtype=np.float64,
    )
    query = np.asarray([[0.1, 0.1]], dtype=np.float64)
    ids, dists = naive_knn(corpus, query, k=2, metric_space=MetricSpace.L2)

    assert ids.shape == (1, 2)
    assert int(ids[0, 0]) == 0
    assert int(ids[0, 1]) == 1
    d_k = float(dists[0, 1])
    assert d_k == pytest.approx(0.905538, abs=1e-6)

    engine_returns = [0, 2]
    # True distances recomputed from corpus (never from the engine).
    returned_true = []
    for rid in engine_returns:
        delta0 = float(corpus[rid, 0]) - 0.1
        delta1 = float(corpus[rid, 1]) - 0.1
        returned_true.append(math.sqrt(delta0 * delta0 + delta1 * delta1))

    recall_id, recall_dist = naive_recall(
        gt_ids=[0, 1],
        returned_ids=engine_returns,
        returned_true_distances=returned_true,
        d_k=d_k,
        n_eff=2,
    )
    assert recall_id == 0.5
    assert recall_dist == 1.0


def test_fixture_b_naive_nk() -> None:
    """Fixture B — §3.7: 1D, k_hub=1, S=4 → N_k = [1, 2, 1, 0]."""
    points = np.asarray([[0.0], [1.0], [2.0], [10.0]], dtype=np.float64)
    n_k = naive_nk(points, k=1, metric_space=MetricSpace.L2)
    assert [int(x) for x in n_k] == [1, 2, 1, 0]
    assert int(sum(int(x) for x in n_k)) == 4  # == S * k_hub
    antihub_fraction = sum(1 for x in n_k if int(x) == 0) / float(len(n_k))
    assert antihub_fraction == 0.25
    # ceil(0.01*4) == 1 vector; id1 holds 2 of 4 slots.
    top = sorted((int(x) for x in n_k), reverse=True)
    hub_share = top[0] / 4.0
    assert hub_share == 0.5


def test_fixture_c_naive_cv() -> None:
    """Fixture C — §5.4: pathological IVF cell among three healthy ones."""
    sizes = [500, 500, 500, 80000]
    cv = naive_cv(sizes)
    mean = sum(sizes) / float(len(sizes))
    # Closed-form population std (ddof=0), not sample std.
    var = sum((s - mean) ** 2 for s in sizes) / float(len(sizes))
    expected_cv = math.sqrt(var) / mean
    assert cv == pytest.approx(expected_cv)
    assert cv == pytest.approx(1.6895464932727084)
    max_over_mean = max(sizes) / mean
    assert max_over_mean == pytest.approx(3.9263803680981595)


def test_naive_knn_three_metric_spaces_and_id_tiebreak() -> None:
    """All three spaces: lower-is-better score, ties by ascending ID (§1.1-1.2)."""
    # Two identical vectors at ids 0 and 1; a farther one at id 2.
    corpus = np.asarray(
        [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        dtype=np.float64,
    )
    query = np.asarray([[1.0, 0.0]], dtype=np.float64)

    for space in (MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT):
        ids, dists = naive_knn(corpus, query, k=2, metric_space=space)
        assert int(ids[0, 0]) == 0  # ascending ID wins the exact tie
        assert int(ids[0, 1]) == 1
        assert float(dists[0, 0]) <= float(dists[0, 1])


def test_naive_nk_three_metric_spaces_sum_invariant() -> None:
    """sum(N_k) == S * k_hub for every metric space (§3.1)."""
    # Unit vectors so COSINE / DOT rankings are well-defined.
    corpus = np.asarray(
        [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, -1.0]],
        dtype=np.float64,
    )
    k_hub = 2
    for space in (MetricSpace.L2, MetricSpace.COSINE, MetricSpace.DOT):
        n_k = naive_nk(corpus, k=k_hub, metric_space=space)
        assert int(sum(int(x) for x in n_k)) == len(corpus) * k_hub
