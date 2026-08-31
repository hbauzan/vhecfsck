"""Unit tests for tombstone layer resolution and ghost neighbourhoods (P6-05)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.tombstones import (
    COUNT_ONLY,
    NO_DELETION_CAPABILITY,
    assert_no_fabricated_tombstones,
    ghost_neighbourhood,
    resolve_tombstone_layer,
)
from vhecfsck.models import MetricSpace, VectorBatch
from vhecfsck.models.scene import PointClass

# --- layer resolution --------------------------------------------------------


def test_absent_capability_yields_no_count_and_an_explanation() -> None:
    """The common case: the engine cannot even say how many are deleted."""
    layer = resolve_tombstone_layer(report_deleted_counts=False, deleted=None)

    assert layer.renderable is False
    assert layer.count is None
    assert layer.reason == NO_DELETION_CAPABILITY


def test_capability_without_positions_yields_a_count_badge() -> None:
    layer = resolve_tombstone_layer(report_deleted_counts=True, deleted=4_812)

    assert layer.renderable is False
    assert layer.count == 4_812
    assert layer.reason == COUNT_ONLY


def test_capability_with_real_positions_is_renderable() -> None:
    layer = resolve_tombstone_layer(
        report_deleted_counts=True, deleted=12, positions_available=True
    )

    assert layer.renderable is True
    assert layer.count == 12
    assert layer.reason is None


def test_capability_true_but_count_missing_is_still_unavailable() -> None:
    layer = resolve_tombstone_layer(report_deleted_counts=True, deleted=None)

    assert layer.renderable is False
    assert layer.count is None


def test_zero_deletions_is_a_real_count_not_a_missing_one() -> None:
    layer = resolve_tombstone_layer(report_deleted_counts=True, deleted=0)

    assert layer.count == 0
    assert layer.reason == COUNT_ONLY


# --- the never-fabricate guard -----------------------------------------------


def test_guard_rejects_tombstone_points_the_layer_may_not_draw() -> None:
    """Invented tombstone positions would look exactly like evidence."""
    classes = np.array(
        [PointClass.HEALTHY.value, PointClass.TOMBSTONE.value], dtype=np.uint8
    )
    layer = resolve_tombstone_layer(report_deleted_counts=True, deleted=1)

    with pytest.raises(ValueError, match="fabricated"):
        assert_no_fabricated_tombstones(classes, layer)


def test_guard_allows_tombstone_points_when_positions_were_read() -> None:
    classes = np.array([PointClass.TOMBSTONE.value], dtype=np.uint8)
    layer = resolve_tombstone_layer(
        report_deleted_counts=True, deleted=1, positions_available=True
    )

    assert_no_fabricated_tombstones(classes, layer)


def test_guard_allows_a_scene_with_no_tombstone_points() -> None:
    classes = np.array([PointClass.HEALTHY.value] * 5, dtype=np.uint8)
    layer = resolve_tombstone_layer(report_deleted_counts=False, deleted=None)

    assert_no_fabricated_tombstones(classes, layer)


# --- ghost neighbourhood -----------------------------------------------------


def _corpus(n: int = 60, d: int = 6, seed: int = 8) -> VectorBatch:
    rng = np.random.default_rng(seed)
    vectors = np.ascontiguousarray(
        rng.normal(size=(n, d)).astype(np.float32), dtype=np.float32
    )
    return VectorBatch(ids=np.arange(n, dtype=np.int64), vectors=vectors)


def test_ghost_neighbourhood_splits_live_from_dead() -> None:
    batch = _corpus()

    everything = ghost_neighbourhood(
        query_id=5,
        corpus_batches=[batch],
        tombstoned_ids=frozenset(),
        metric_space=MetricSpace.L2,
        k=6,
    )
    dead_ids = frozenset(everything.live_neighbours[:2])

    blocked = ghost_neighbourhood(
        query_id=5,
        corpus_batches=[batch],
        tombstoned_ids=dead_ids,
        metric_space=MetricSpace.L2,
        k=6,
    )

    assert set(blocked.dead_neighbours) == dead_ids
    assert not set(blocked.live_neighbours) & dead_ids
    assert len(blocked.dead_neighbours) + len(blocked.live_neighbours) == 6


def test_blocked_fraction_reflects_the_dead_share() -> None:
    batch = _corpus()
    baseline = ghost_neighbourhood(
        query_id=2,
        corpus_batches=[batch],
        tombstoned_ids=frozenset(),
        metric_space=MetricSpace.L2,
        k=4,
    )

    assert baseline.blocked_fraction == pytest.approx(0.0)

    blocked = ghost_neighbourhood(
        query_id=2,
        corpus_batches=[batch],
        tombstoned_ids=frozenset(baseline.live_neighbours),
        metric_space=MetricSpace.L2,
        k=4,
    )

    assert blocked.blocked_fraction == pytest.approx(1.0)


def test_ghost_neighbourhood_excludes_the_query_itself() -> None:
    batch = _corpus()

    view = ghost_neighbourhood(
        query_id=7,
        corpus_batches=[batch],
        tombstoned_ids=frozenset({7}),
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert 7 not in view.dead_neighbours
    assert 7 not in view.live_neighbours


def test_ghost_neighbourhood_of_an_absent_id_degrades_gracefully() -> None:
    view = ghost_neighbourhood(
        query_id=9_999,
        corpus_batches=[_corpus()],
        tombstoned_ids=frozenset(),
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert view.available is False
    assert view.unavailable_reason is not None


def test_ghost_neighbourhood_of_an_empty_corpus_degrades_gracefully() -> None:
    view = ghost_neighbourhood(
        query_id=1,
        corpus_batches=[],
        tombstoned_ids=frozenset(),
        metric_space=MetricSpace.L2,
        k=5,
    )

    assert view.available is False


def test_ghost_neighbourhood_rejects_a_non_positive_k() -> None:
    with pytest.raises(ValueError, match="k must be >= 1"):
        ghost_neighbourhood(
            query_id=1,
            corpus_batches=[_corpus()],
            tombstoned_ids=frozenset(),
            metric_space=MetricSpace.L2,
            k=0,
        )
