"""Unit tests for report-derived camera presets and the guided tour (P6-06)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.camera import (
    ANTIHUB_PERIPHERY,
    HUB_CLUSTER,
    OVERVIEW,
    PRESET_NAMES,
    WORST_PARTITION,
    build_tour,
    derive_presets,
    sample_tour,
    worst_partition_id,
)
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload


def _golden_scene(
    *,
    with_hubs: bool = True,
    with_antihubs: bool = True,
    with_partitions: bool = True,
) -> ScenePayload:
    """A fixed scene standing in for a golden report."""
    rng = np.random.default_rng(4)
    n = 200
    positions = rng.uniform(-1.0, 1.0, size=(n, 3)).astype(np.float32)

    # Hubs sit in a tight knot; anti-hubs sit far out on one side.
    classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
    if with_hubs:
        positions[0:8] = np.array([0.4, 0.4, 0.4], dtype=np.float32)
        positions[0:8] += rng.normal(scale=0.02, size=(8, 3)).astype(np.float32)
        classes[0:8] = PointClass.HUB.value
    if with_antihubs:
        positions[8:14] = np.array([-0.9, -0.8, 0.1], dtype=np.float32)
        classes[8:14] = PointClass.ANTIHUB.value

    partition = None
    if with_partitions:
        partition = np.zeros(n, dtype=np.int32)
        partition[:150] = 2  # the oversized cell
        partition[150:180] = 1
        partition[180:] = 3

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
        partition_id=partition,
    )


# --- presets -----------------------------------------------------------------


def test_every_preset_name_is_derived() -> None:
    presets = derive_presets(_golden_scene())

    assert set(presets) == set(PRESET_NAMES)
    assert all(p.available for p in presets.values())


def test_presets_are_stable_for_a_golden_scene() -> None:
    """The property the recording depends on: same report, same transform."""
    first = derive_presets(_golden_scene())
    second = derive_presets(_golden_scene())

    for name in PRESET_NAMES:
        assert first[name].position == second[name].position
        assert first[name].target == second[name].target


def test_hub_preset_aims_at_the_hubs_not_at_the_origin() -> None:
    presets = derive_presets(_golden_scene())

    target = presets[HUB_CLUSTER].target

    assert target[0] == pytest.approx(0.4, abs=0.05)
    assert target[1] == pytest.approx(0.4, abs=0.05)
    assert presets[OVERVIEW].target != target


def test_antihub_preset_aims_at_the_periphery() -> None:
    presets = derive_presets(_golden_scene())

    assert presets[ANTIHUB_PERIPHERY].target[0] == pytest.approx(-0.9, abs=0.05)


def test_a_tight_cluster_is_framed_closer_than_the_whole_cloud() -> None:
    presets = derive_presets(_golden_scene())

    def _distance(name: str) -> float:
        preset = presets[name]
        return float(
            np.linalg.norm(np.asarray(preset.position) - np.asarray(preset.target))
        )

    assert _distance(HUB_CLUSTER) < _distance(OVERVIEW)


def test_worst_partition_is_the_largest_cell() -> None:
    assert worst_partition_id(_golden_scene()) == 2


def test_worst_partition_is_unavailable_without_partition_data() -> None:
    presets = derive_presets(_golden_scene(with_partitions=False))

    assert presets[WORST_PARTITION].available is False
    assert presets[WORST_PARTITION].unavailable_reason is not None
    assert worst_partition_id(_golden_scene(with_partitions=False)) is None


def test_missing_hubs_disable_the_hub_preset_with_a_reason() -> None:
    presets = derive_presets(_golden_scene(with_hubs=False))

    assert presets[HUB_CLUSTER].available is False
    assert "hubs" in str(presets[HUB_CLUSTER].unavailable_reason)
    assert presets[OVERVIEW].available is True


# --- tour --------------------------------------------------------------------


def test_tour_visits_only_available_presets_in_narrative_order() -> None:
    presets = derive_presets(_golden_scene(with_hubs=False))

    timeline = build_tour(presets)

    assert [s.preset for s in timeline.steps] == [
        OVERVIEW,
        ANTIHUB_PERIPHERY,
        WORST_PARTITION,
    ]


def test_the_opening_shot_does_not_fly_in() -> None:
    timeline = build_tour(derive_presets(_golden_scene()))

    assert timeline.steps[0].transition_seconds == 0.0
    assert timeline.steps[1].transition_seconds > 0.0


def test_tour_refuses_to_script_a_scene_with_nothing_to_show() -> None:
    empty = ScenePayload(
        positions=np.empty((0, 3), dtype=np.float32),
        classes=np.empty(0, dtype=np.uint8),
        ids=np.empty(0, dtype=np.int64),
        lod=LodMetadata(
            requested_budget=1,
            actual_count=0,
            decimation_method="none",
            complete=True,
            has_tombstones=False,
        ),
    )

    with pytest.raises(ValueError, match="no preset is available"):
        build_tour(derive_presets(empty))


def test_tour_rejects_a_non_positive_frame_rate() -> None:
    with pytest.raises(ValueError, match="fps must be >= 1"):
        build_tour(derive_presets(_golden_scene()), fps=0)


def test_frame_count_matches_the_declared_timeline() -> None:
    presets = derive_presets(_golden_scene())
    timeline = build_tour(presets, fps=30, transition_seconds=1.0, hold_seconds=2.0)

    frames = sample_tour(timeline, presets)

    # 4 presets: 3 transitions of 30 frames plus 4 holds of 60.
    assert timeline.total_frames == 3 * 30 + 4 * 60
    assert len(frames) == timeline.total_frames
    assert timeline.duration_seconds == pytest.approx(11.0)


def test_the_tour_is_frame_deterministic() -> None:
    """Two runs produce identical frames — the recording's whole premise."""
    presets = derive_presets(_golden_scene())
    timeline = build_tour(presets)

    first = sample_tour(timeline, presets)
    second = sample_tour(timeline, presets)

    assert [f.position for f in first] == [f.position for f in second]
    assert [f.caption for f in first] == [f.caption for f in second]


def test_the_tour_runs_to_completion_at_the_last_preset() -> None:
    presets = derive_presets(_golden_scene())
    timeline = build_tour(presets)

    frames = sample_tour(timeline, presets)

    assert frames[-1].holding is True
    assert frames[-1].preset == timeline.steps[-1].preset
    assert frames[-1].position == presets[frames[-1].preset].position


def test_frame_indices_and_times_advance_monotonically() -> None:
    presets = derive_presets(_golden_scene())
    timeline = build_tour(presets, fps=24)

    frames = sample_tour(timeline, presets)

    assert [f.index for f in frames] == list(range(len(frames)))
    times = [f.time_seconds for f in frames]
    assert times == sorted(times)


def test_transition_frames_end_on_the_destination() -> None:
    presets = derive_presets(_golden_scene())
    timeline = build_tour(presets, fps=10, transition_seconds=1.0, hold_seconds=0.1)

    frames = sample_tour(timeline, presets)
    moving = [f for f in frames if not f.holding]

    assert moving, "a multi-preset tour must contain transition frames"
    last_of_first_transition = moving[9]
    destination = presets[last_of_first_transition.preset].position
    for axis in range(3):
        assert last_of_first_transition.position[axis] == pytest.approx(
            destination[axis], abs=1e-9
        )
