"""Unit tests for colour-by attribute buffers and distribution charts (P6-04)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.hubness import bucketed_histogram
from vhecfsck.core.scene_views import (
    NK_UNAVAILABLE,
    PARTITION_UNAVAILABLE,
    build_distribution_charts,
    colour_attribute,
    distances_to_centroid,
    partition_size_histogram,
)
from vhecfsck.models.scene import ColourBy, LodMetadata, PointClass, ScenePayload


def _scene(
    n: int = 60,
    *,
    with_partition: bool = True,
    with_nk: bool = True,
    seed: int = 5,
) -> ScenePayload:
    rng = np.random.default_rng(seed)
    positions = rng.uniform(-1.0, 1.0, size=(n, 3)).astype(np.float32)
    classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
    classes[:3] = PointClass.HUB.value
    classes[3:6] = PointClass.ANTIHUB.value

    return ScenePayload(
        positions=positions,
        classes=classes,
        ids=np.arange(n, dtype=np.int64),
        lod=LodMetadata(
            requested_budget=n,
            actual_count=n,
            decimation_method="none",
            complete=True,
            has_tombstones=False,
        ),
        partition_id=(
            rng.integers(0, 4, size=n).astype(np.int32) if with_partition else None
        ),
        nk=rng.integers(0, 30, size=n).astype(np.int32) if with_nk else None,
    )


# --- distance to centroid ----------------------------------------------------


def test_distance_to_centroid_is_zero_at_the_centroid() -> None:
    positions = np.array(
        [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32
    )

    distances = distances_to_centroid(positions)

    assert float(distances[2]) == pytest.approx(0.0, abs=1e-6)
    assert float(distances[0]) == pytest.approx(1.0, abs=1e-6)
    assert float(distances[1]) == pytest.approx(1.0, abs=1e-6)


def test_distance_to_centroid_handles_an_empty_scene() -> None:
    assert distances_to_centroid(np.empty((0, 3), dtype=np.float32)).shape == (0,)


def test_distance_to_centroid_is_never_negative() -> None:
    rng = np.random.default_rng(3)
    positions = rng.uniform(-1.0, 1.0, size=(500, 3)).astype(np.float32)

    distances = distances_to_centroid(positions)

    assert float(distances.min()) >= 0.0


# --- colour-by modes ---------------------------------------------------------


def test_each_mode_produces_a_distinct_buffer() -> None:
    scene = _scene()

    buffers = {
        mode: colour_attribute(scene, mode).values.tobytes() for mode in ColourBy
    }

    assert len(set(buffers.values())) == len(ColourBy)


def test_class_mode_is_categorical_and_matches_the_class_array() -> None:
    scene = _scene()

    attr = colour_attribute(scene, ColourBy.CLASS)

    assert attr.available is True
    assert attr.categorical is True
    assert attr.values.tobytes() == scene.classes.astype(np.float32).tobytes()


def test_partition_mode_is_disabled_with_a_reason_when_unavailable() -> None:
    """A missing capability disables the mode; it never colours points wrong."""
    scene = _scene(with_partition=False)

    attr = colour_attribute(scene, ColourBy.PARTITION)

    assert attr.available is False
    assert attr.unavailable_reason == PARTITION_UNAVAILABLE
    assert attr.values.shape == (0,)


def test_nk_mode_is_disabled_with_a_reason_when_unavailable() -> None:
    scene = _scene(with_nk=False)

    attr = colour_attribute(scene, ColourBy.NK)

    assert attr.available is False
    assert attr.unavailable_reason == NK_UNAVAILABLE


def test_continuous_modes_are_normalised_to_the_unit_interval() -> None:
    scene = _scene()

    for mode in (ColourBy.NK, ColourBy.DISTANCE_TO_CENTROID):
        attr = colour_attribute(scene, mode)
        assert attr.categorical is False
        assert float(attr.values.min()) >= 0.0
        assert float(attr.values.max()) <= 1.0
        assert attr.domain[0] <= attr.domain[1]


def test_constant_attribute_normalises_without_dividing_by_zero() -> None:
    scene = _scene(n=10)
    flat = ScenePayload(
        positions=scene.positions,
        classes=scene.classes,
        ids=scene.ids,
        lod=scene.lod,
        nk=np.full(10, 7, dtype=np.int32),
    )

    attr = colour_attribute(flat, ColourBy.NK)

    assert attr.available is True
    assert float(attr.values.max()) == 0.0
    assert attr.domain == (7.0, 7.0)


def test_distance_mode_prefers_the_precomputed_buffer() -> None:
    scene = _scene(n=12)
    supplied = np.linspace(0.0, 4.0, 12).astype(np.float32)
    with_buffer = ScenePayload(
        positions=scene.positions,
        classes=scene.classes,
        ids=scene.ids,
        lod=scene.lod,
        dist_centroid=supplied,
    )

    attr = colour_attribute(with_buffer, ColourBy.DISTANCE_TO_CENTROID)

    assert attr.domain == (0.0, 4.0)


def test_every_mode_is_unavailable_on_an_empty_scene() -> None:
    empty = ScenePayload(
        positions=np.empty((0, 3), dtype=np.float32),
        classes=np.empty(0, dtype=np.uint8),
        ids=np.empty(0, dtype=np.int64),
        lod=LodMetadata(
            requested_budget=10,
            actual_count=0,
            decimation_method="none",
            complete=True,
            has_tombstones=False,
        ),
    )

    for mode in ColourBy:
        assert colour_attribute(empty, mode).available is False


# --- charts ------------------------------------------------------------------


def test_nk_histogram_matches_the_reports_bucketing_exactly() -> None:
    """The panel draws what the report publishes — one bucketing, not two."""
    rng = np.random.default_rng(11)
    n_k = rng.integers(0, 400, size=2_000).astype(np.int64)

    charts = build_distribution_charts(n_k, partition_sizes=[10, 20, 30])

    assert list(charts.nk_histogram) == bucketed_histogram(n_k)


def test_nk_axis_is_logarithmic() -> None:
    charts = build_distribution_charts([0, 1, 2], partition_sizes=None)

    assert charts.nk_log_y is True


def test_partition_chart_reports_the_mean() -> None:
    buckets, mean = partition_size_histogram([10, 20, 30, 40])

    assert mean == pytest.approx(25.0)
    assert sum(b["count"] for b in buckets) == 4


def test_partition_chart_is_absent_with_a_reason_when_unavailable() -> None:
    charts = build_distribution_charts([1, 2, 3], partition_sizes=None)

    assert charts.partition_histogram is None
    assert charts.partition_mean is None
    assert charts.partition_unavailable_reason == PARTITION_UNAVAILABLE


def test_empty_partition_sizes_produce_no_buckets() -> None:
    buckets, mean = partition_size_histogram([])

    assert buckets == ()
    assert mean == 0.0


def test_histogram_bucket_counts_sum_to_the_sample_size() -> None:
    rng = np.random.default_rng(2)
    n_k = rng.integers(0, 5_000, size=1_500).astype(np.int64)

    charts = build_distribution_charts(n_k, partition_sizes=None)

    assert sum(b["count"] for b in charts.nk_histogram) == 1_500
