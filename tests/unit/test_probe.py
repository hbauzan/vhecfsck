"""Unit tests for the single-query probe and the inverse hub view (P6-03)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.probe import (
    MAX_CANNIBALISED_QUERIES,
    hub_cannibalisation,
    probe_point,
)
from vhecfsck.models import MetricSpace, VectorBatch


def _corpus(n: int = 120, d: int = 8, seed: int = 19) -> VectorBatch:
    rng = np.random.default_rng(seed)
    vectors = np.ascontiguousarray(
        rng.normal(size=(n, d)).astype(np.float32), dtype=np.float32
    )
    return VectorBatch(ids=np.arange(n, dtype=np.int64), vectors=vectors)


def _exact_neighbours(batch: VectorBatch, query_id: int, k: int) -> list[int]:
    """Ground truth computed directly, self-excluded, for cross-checking."""
    row = int(np.flatnonzero(batch.ids == query_id)[0])
    result = exact_knn(
        [batch],
        batch.vectors[row : row + 1],
        k + 1,
        MetricSpace.L2,
        n_total=int(batch.ids.shape[0]),
    )
    out: list[int] = []
    for column in range(int(result.ids.shape[1])):
        candidate = int(result.ids[0, column])
        if candidate < 0 or candidate == query_id:
            continue
        out.append(candidate)
        if len(out) >= k:
            break
    return out


# --- ground truth agreement --------------------------------------------------


def test_probe_ground_truth_matches_core_ground_truth_exactly() -> None:
    """The probe and the oracle must never disagree for the same point."""
    batch = _corpus()

    result = probe_point(
        query_id=17,
        corpus_batches=[batch],
        returned_ids=[],
        metric_space=MetricSpace.L2,
        k=10,
    )

    assert list(result.true_neighbours) == _exact_neighbours(batch, 17, 10)


def test_probe_excludes_the_query_from_its_own_ground_truth() -> None:
    batch = _corpus()

    result = probe_point(
        query_id=3,
        corpus_batches=[batch],
        returned_ids=[3, 4, 5],
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert 3 not in result.true_neighbours
    assert 3 not in result.engine_returned


def test_true_distances_are_ascending() -> None:
    batch = _corpus()

    result = probe_point(
        query_id=42,
        corpus_batches=[batch],
        returned_ids=[],
        metric_space=MetricSpace.L2,
        k=8,
    )

    distances = list(result.true_distances)
    assert distances == sorted(distances)
    assert len(distances) == len(result.true_neighbours)


# --- the comparison ----------------------------------------------------------


def test_a_perfect_engine_misses_nothing() -> None:
    batch = _corpus()
    truth = _exact_neighbours(batch, 8, 6)

    result = probe_point(
        query_id=8,
        corpus_batches=[batch],
        returned_ids=truth,
        metric_space=MetricSpace.L2,
        k=6,
    )

    assert result.missed == ()
    assert result.dead_returns == ()
    assert result.unexpected == ()
    assert result.recall_id == pytest.approx(1.0)


def test_missed_neighbours_are_the_set_difference() -> None:
    batch = _corpus()
    truth = _exact_neighbours(batch, 8, 6)

    result = probe_point(
        query_id=8,
        corpus_batches=[batch],
        returned_ids=truth[:3],
        metric_space=MetricSpace.L2,
        k=6,
    )

    assert set(result.missed) == set(truth[3:])
    assert result.recall_id == pytest.approx(0.5)


def test_tombstoned_probe_shows_missed_neighbours_and_dead_returns() -> None:
    """Splice a dead id into the return row, the way a leaking engine would.

    The adapter post-filters dead ids, so the failure mode the probe exists to
    render has to be injected rather than waited for (lessons-learned §33).
    """
    batch = _corpus()
    truth = _exact_neighbours(batch, 55, 6)
    dead_id = 9_999
    engine_row = [truth[0], dead_id, truth[1]]

    result = probe_point(
        query_id=55,
        corpus_batches=[batch],
        returned_ids=engine_row,
        metric_space=MetricSpace.L2,
        k=6,
    )

    assert result.dead_returns == (dead_id,)
    assert set(result.missed) == set(truth[2:])
    assert dead_id not in result.unexpected


def test_live_but_wrong_returns_are_unexpected_not_dead() -> None:
    batch = _corpus()
    truth = _exact_neighbours(batch, 20, 4)
    intruder = next(i for i in range(120) if i not in truth and i != 20)

    result = probe_point(
        query_id=20,
        corpus_batches=[batch],
        returned_ids=[truth[0], intruder],
        metric_space=MetricSpace.L2,
        k=4,
    )

    assert result.unexpected == (intruder,)
    assert result.dead_returns == ()


def test_padding_and_duplicates_are_ignored_in_the_engine_row() -> None:
    batch = _corpus()
    truth = _exact_neighbours(batch, 11, 4)

    result = probe_point(
        query_id=11,
        corpus_batches=[batch],
        returned_ids=[truth[0], truth[0], -1, -1, truth[1]],
        metric_space=MetricSpace.L2,
        k=4,
    )

    assert result.engine_returned == (truth[0], truth[1])


def test_n_k_is_carried_through_when_supplied() -> None:
    batch = _corpus()

    result = probe_point(
        query_id=1,
        corpus_batches=[batch],
        returned_ids=[],
        metric_space=MetricSpace.L2,
        k=3,
        n_k=137,
    )

    assert result.n_k == 137


# --- graceful degradation ----------------------------------------------------


def test_probing_an_id_deleted_mid_session_degrades_gracefully() -> None:
    batch = _corpus()

    result = probe_point(
        query_id=10_000,
        corpus_batches=[batch],
        returned_ids=[1, 2],
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert result.available is False
    assert result.unavailable_reason is not None
    assert "10000" in result.unavailable_reason
    assert result.true_neighbours == ()


def test_probing_an_empty_corpus_degrades_gracefully() -> None:
    result = probe_point(
        query_id=1,
        corpus_batches=[],
        returned_ids=[],
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert result.available is False
    assert result.unavailable_reason is not None


def test_k_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="k must be >= 1"):
        probe_point(
            query_id=1,
            corpus_batches=[_corpus()],
            returned_ids=[],
            metric_space=MetricSpace.L2,
            k=0,
        )


def test_k_larger_than_the_corpus_is_clamped_not_crashed() -> None:
    batch = _corpus(n=6)

    result = probe_point(
        query_id=0,
        corpus_batches=[batch],
        returned_ids=[],
        metric_space=MetricSpace.L2,
        k=50,
    )

    assert result.available is True
    assert len(result.true_neighbours) == 5


# --- inverse hub view --------------------------------------------------------


def test_hub_cannibalisation_lists_the_queries_landing_on_a_hub() -> None:
    neighbours = np.array(
        [[7, 1], [7, 2], [3, 4], [7, 5]],
        dtype=np.int64,
    )
    queries = np.array([100, 101, 102, 103], dtype=np.int64)

    view = hub_cannibalisation(hub_id=7, neighbour_ids=neighbours, query_ids=queries)

    assert view.query_ids == (100, 101, 103)
    assert view.n_k == 3
    assert view.truncated is False


def test_hub_cannibalisation_excludes_a_self_match() -> None:
    neighbours = np.array([[7, 1], [7, 2]], dtype=np.int64)
    queries = np.array([7, 101], dtype=np.int64)

    view = hub_cannibalisation(hub_id=7, neighbour_ids=neighbours, query_ids=queries)

    assert view.query_ids == (101,)


def test_hub_cannibalisation_caps_the_transported_list() -> None:
    rows = MAX_CANNIBALISED_QUERIES + 25
    neighbours = np.full((rows, 2), 7, dtype=np.int64)
    queries = np.arange(1_000, 1_000 + rows, dtype=np.int64)

    view = hub_cannibalisation(hub_id=7, neighbour_ids=neighbours, query_ids=queries)

    assert view.n_k == rows
    assert len(view.query_ids) == MAX_CANNIBALISED_QUERIES
    assert view.truncated is True


def test_hub_cannibalisation_rejects_a_length_mismatch() -> None:
    with pytest.raises(ValueError, match="query_ids"):
        hub_cannibalisation(
            hub_id=1,
            neighbour_ids=np.zeros((3, 2), dtype=np.int64),
            query_ids=np.zeros(2, dtype=np.int64),
        )


def test_hub_cannibalisation_rejects_a_non_matrix() -> None:
    with pytest.raises(ValueError, match="2-D"):
        hub_cannibalisation(
            hub_id=1,
            neighbour_ids=np.zeros(4, dtype=np.int64),
            query_ids=np.zeros(4, dtype=np.int64),
        )
