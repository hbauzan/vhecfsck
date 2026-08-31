"""Unit tests for progressive chunked decimation and budget guards (P6-01)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.core.lod import (
    COARSE_CHUNK_POINTS,
    DEFAULT_DISPLAY_BUDGET,
    HARD_MAX_DISPLAY_BUDGET,
    decimate,
    decimate_chunk,
    plan_chunks,
    resolve_display_budget,
    selection_order,
)
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload

PRIORITY_CLASSES = (
    PointClass.HUB.value,
    PointClass.ANTIHUB.value,
    PointClass.QUERY.value,
    PointClass.TRUE_NEIGHBOUR.value,
    PointClass.RETURNED.value,
    PointClass.MISSED.value,
)


def _make_scene(
    n_healthy: int,
    n_hubs: int,
    n_antihubs: int,
    n_tombstones: int = 0,
    seed: int = 42,
) -> ScenePayload:
    n_total = n_healthy + n_hubs + n_antihubs + n_tombstones
    rng = np.random.default_rng(seed)
    positions = rng.uniform(-1.0, 1.0, size=(n_total, 3)).astype(np.float32)

    # Interleave so priority points are never contiguous at the head; a chunker
    # that simply slices the input would pass otherwise.
    classes = np.full(n_total, PointClass.HEALTHY.value, dtype=np.uint8)
    stride = max(1, n_total // max(1, n_hubs + n_antihubs + n_tombstones))
    cursor = 0
    for value, count in (
        (PointClass.HUB.value, n_hubs),
        (PointClass.ANTIHUB.value, n_antihubs),
        (PointClass.TOMBSTONE.value, n_tombstones),
    ):
        for _ in range(count):
            classes[min(cursor, n_total - 1)] = value
            cursor += stride

    return ScenePayload(
        positions=positions,
        classes=classes,
        ids=np.arange(n_total, dtype=np.int64),
        lod=LodMetadata(
            requested_budget=n_total,
            actual_count=n_total,
            decimation_method="none",
            complete=True,
            has_tombstones=n_tombstones > 0,
        ),
    )


# --- Budget guard ------------------------------------------------------------


def test_default_budget_is_accepted_on_a_capable_device() -> None:
    decision = resolve_display_budget(
        DEFAULT_DISPLAY_BUDGET, device_max_points=1_000_000
    )

    assert decision.accepted is True
    assert decision.granted == DEFAULT_DISPLAY_BUDGET
    assert decision.reason is None


def test_budget_beyond_device_capability_is_refused_with_a_reason() -> None:
    """The guard refuses rather than letting the tab hang (P6-01)."""
    decision = resolve_display_budget(900_000, device_max_points=250_000)

    assert decision.accepted is False
    assert decision.granted == 250_000
    assert decision.reason is not None
    assert "250000" in decision.reason.replace(",", "")


def test_budget_beyond_the_hard_ceiling_is_refused() -> None:
    decision = resolve_display_budget(
        HARD_MAX_DISPLAY_BUDGET + 1, device_max_points=10_000_000
    )

    assert decision.accepted is False
    assert decision.granted == HARD_MAX_DISPLAY_BUDGET


def test_budget_must_be_positive() -> None:
    with pytest.raises(ValueError, match="budget must be >= 1"):
        resolve_display_budget(0, device_max_points=100)


# --- Chunk planning ----------------------------------------------------------


def test_first_chunk_is_the_coarse_scene() -> None:
    """Something appears immediately: chunk 0 is bounded by the coarse size."""
    plan = plan_chunks(total_available=1_000_000, budget=200_000)

    assert plan.chunk_sizes[0] == COARSE_CHUNK_POINTS
    assert plan.chunk_count >= 2


def test_chunk_sizes_sum_to_the_granted_budget() -> None:
    plan = plan_chunks(total_available=1_000_000, budget=200_000)

    assert sum(plan.chunk_sizes) == 200_000
    assert plan.budget == 200_000
    assert plan.total_available == 1_000_000


def test_small_corpus_is_a_single_complete_chunk() -> None:
    plan = plan_chunks(total_available=1_200, budget=200_000)

    assert plan.chunk_count == 1
    assert plan.chunk_sizes == (1_200,)


def test_plan_never_promises_more_points_than_exist() -> None:
    plan = plan_chunks(total_available=70_000, budget=1_000_000)

    assert sum(plan.chunk_sizes) == 70_000


# --- Progressive selection ---------------------------------------------------


def test_hubs_and_antihubs_arrive_in_the_first_chunk() -> None:
    """The findings are visible before the background is (P6-01)."""
    scene = _make_scene(n_healthy=40_000, n_hubs=120, n_antihubs=60, seed=7)
    plan = plan_chunks(total_available=len(scene.positions), budget=20_000)

    first = decimate_chunk(scene, plan=plan, chunk_index=0, seed=11)

    hubs = int(np.sum(first.classes == PointClass.HUB.value))
    antihubs = int(np.sum(first.classes == PointClass.ANTIHUB.value))
    assert hubs == 120
    assert antihubs == 60


def test_chunks_are_disjoint_and_cover_the_whole_selection() -> None:
    scene = _make_scene(n_healthy=8_000, n_hubs=40, n_antihubs=20, seed=3)
    plan = plan_chunks(
        total_available=len(scene.positions),
        budget=4_000,
        coarse_points=1_000,
        refinement_points=1_000,
    )
    assert plan.chunk_count == 4

    seen: list[int] = []
    for i in range(plan.chunk_count):
        chunk = decimate_chunk(scene, plan=plan, chunk_index=i, seed=5)
        assert chunk.lod.chunk_index == i
        assert chunk.lod.chunk_count == plan.chunk_count
        seen.extend(int(x) for x in chunk.ids)

    assert len(seen) == len(set(seen)), "chunks must not repeat a point"
    assert len(seen) == sum(plan.chunk_sizes)

    order = selection_order(scene, budget=4_000, seed=5)
    assert set(seen) == {int(scene.ids[i]) for i in order}


def test_only_the_last_chunk_is_marked_complete() -> None:
    scene = _make_scene(n_healthy=8_000, n_hubs=10, n_antihubs=10, seed=3)
    plan = plan_chunks(
        total_available=len(scene.positions),
        budget=4_000,
        coarse_points=1_000,
        refinement_points=1_000,
    )

    for i in range(plan.chunk_count):
        chunk = decimate_chunk(scene, plan=plan, chunk_index=i, seed=5)
        assert chunk.lod.complete is (i == plan.chunk_count - 1)
        assert chunk.lod.total_available == len(scene.positions)


def test_chunking_is_deterministic_under_a_seed() -> None:
    scene = _make_scene(n_healthy=5_000, n_hubs=20, n_antihubs=10, seed=3)
    plan = plan_chunks(
        total_available=len(scene.positions),
        budget=2_000,
        coarse_points=500,
        refinement_points=500,
    )

    a = decimate_chunk(scene, plan=plan, chunk_index=2, seed=99)
    b = decimate_chunk(scene, plan=plan, chunk_index=2, seed=99)

    assert a.ids.tobytes() == b.ids.tobytes()
    assert a.positions.tobytes() == b.positions.tobytes()


def test_chunk_index_out_of_range_is_rejected() -> None:
    scene = _make_scene(n_healthy=100, n_hubs=2, n_antihubs=2)
    plan = plan_chunks(total_available=104, budget=104)

    with pytest.raises(ValueError, match="chunk_index"):
        decimate_chunk(scene, plan=plan, chunk_index=plan.chunk_count)


def test_selection_order_puts_priority_points_first() -> None:
    scene = _make_scene(n_healthy=2_000, n_hubs=15, n_antihubs=10, seed=21)

    order = selection_order(scene, budget=500, seed=1)
    head = scene.classes[order[:25]]

    assert all(int(c) in PRIORITY_CLASSES for c in head)


def test_selection_order_matches_decimate_as_a_set() -> None:
    """`decimate` and the progressive path select the same points."""
    scene = _make_scene(n_healthy=3_000, n_hubs=12, n_antihubs=8, seed=13)

    order = selection_order(scene, budget=900, seed=4)
    whole = decimate(scene, budget=900, seed=4)

    assert {int(x) for x in whole.ids} == {int(scene.ids[i]) for i in order}


def test_decimate_still_honours_the_budget_at_scale() -> None:
    scene = _make_scene(n_healthy=60_000, n_hubs=200, n_antihubs=100, seed=17)

    out = decimate(scene, budget=25_000, seed=2)

    assert out.lod.actual_count == 25_000
    assert len(out.positions) == 25_000
    assert int(np.sum(out.classes == PointClass.HUB.value)) == 200
