"""Unit tests for scene assembly from an adapter (P6-01, P6-05, P6-06)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.core.camera import OVERVIEW, WORST_PARTITION
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload
from vhecfsck.server.scene_service import (
    assemble_scene,
    build_scene_bundle,
    findings_from_report,
    presets_payload,
)


@pytest.fixture(scope="module")
def healthy_adapter():
    opened = open_scenario("healthy", size="tiny")
    try:
        yield opened.adapter
    finally:
        close = getattr(opened.adapter, "close", None)
        if close is not None:
            close()


def test_bundle_reads_a_scene_from_a_live_adapter(healthy_adapter) -> None:
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert bundle.scene.lod.actual_count > 0
    assert bundle.scene.positions.shape[1] == 3
    assert bundle.scene.dist_centroid is not None
    assert bundle.budget_reason is None


def test_positions_land_inside_the_display_cube(healthy_adapter) -> None:
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert float(np.abs(bundle.scene.positions).max()) <= 1.0 + 1e-5


def test_a_budget_beyond_the_device_is_reported_not_attempted(
    healthy_adapter,
) -> None:
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=900_000, device_max_points=500
    )

    assert bundle.budget_reason is not None
    assert "900000" in bundle.budget_reason
    assert bundle.plan.budget <= 500
    assert bundle.scene.lod.actual_count <= 500


def test_hub_ids_from_a_report_are_painted_as_hubs(healthy_adapter) -> None:
    bundle = build_scene_bundle(
        healthy_adapter,
        requested_budget=1_000,
        device_max_points=1_000_000,
        hub_ids=frozenset({0, 1, 2}),
        antihub_ids=frozenset({3, 4}),
    )

    painted = {
        int(i)
        for i, c in zip(bundle.scene.ids, bundle.scene.classes, strict=True)
        if c == PointClass.HUB.value
    }
    assert painted == {0, 1, 2}


def test_scene_assembly_is_deterministic(healthy_adapter) -> None:
    kwargs = {"requested_budget": 500, "device_max_points": 1_000_000, "seed": 7}

    first = build_scene_bundle(healthy_adapter, **kwargs)
    second = build_scene_bundle(healthy_adapter, **kwargs)

    assert first.scene.ids.tobytes() == second.scene.ids.tobytes()
    assert first.scene.positions.tobytes() == second.scene.positions.tobytes()


def test_the_synthetic_adapter_never_yields_renderable_tombstones(
    healthy_adapter,
) -> None:
    """No engine here can hand back a deleted vector's coordinates."""
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert bundle.tombstones.renderable is False
    assert bundle.tombstones.reason is not None
    assert bundle.scene.lod.has_tombstones is False
    assert int(np.sum(bundle.scene.classes == PointClass.TOMBSTONE.value)) == 0


def test_tombstone_verdict_travels_in_the_lod_metadata(healthy_adapter) -> None:
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert bundle.scene.lod.tombstone_reason == bundle.tombstones.reason
    assert bundle.scene.lod.tombstone_count == bundle.tombstones.count


def test_partition_sizes_reach_the_charts_panel(healthy_adapter) -> None:
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert bundle.partition_sizes is not None
    assert int(bundle.partition_sizes.sum()) > 0


def test_colour_by_partition_is_unavailable_without_per_point_assignments(
    healthy_adapter,
) -> None:
    """Sizes are readable; per-vector cell membership is not. Say so."""
    bundle = build_scene_bundle(
        healthy_adapter, requested_budget=1_000, device_max_points=1_000_000
    )

    assert bundle.scene.partition_id is None


# --- presets -----------------------------------------------------------------


def _scene_with_findings() -> ScenePayload:
    rng = np.random.default_rng(2)
    n = 60
    positions = rng.uniform(-1.0, 1.0, size=(n, 3)).astype(np.float32)
    classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
    classes[:4] = PointClass.HUB.value
    classes[4:8] = PointClass.ANTIHUB.value
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
        partition_id=rng.integers(0, 3, size=n).astype(np.int32),
    )


def test_presets_payload_is_json_safe_and_complete() -> None:
    payload = presets_payload(_scene_with_findings())

    assert set(payload["presets"]) >= {OVERVIEW, WORST_PARTITION}
    overview = payload["presets"][OVERVIEW]
    assert isinstance(overview["position"], list)
    assert all(isinstance(x, float) for x in overview["position"])
    assert overview["available"] is True


def test_presets_payload_carries_a_frame_accurate_tour() -> None:
    payload = presets_payload(_scene_with_findings())

    tour = payload["tour"]
    assert tour is not None
    assert tour["total_frames"] == payload["frame_count"]
    assert tour["steps"][0]["transition_seconds"] == 0.0


def test_presets_payload_omits_the_tour_when_nothing_can_be_shown() -> None:
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

    payload = presets_payload(empty)

    assert payload["tour"] is None
    assert payload["presets"][OVERVIEW]["available"] is False


def test_findings_from_report_read_hubness_detail() -> None:
    report = {
        "metrics": [
            {
                "id": "hub_share_top1pct",
                "detail": {
                    "hub_ids": [1, 2, 2],
                    "antihub_ids": [9],
                    "n_k": [0, 3, 1],
                },
            }
        ]
    }

    hubs, antis, n_k = findings_from_report(report)

    assert hubs == frozenset({1, 2})
    assert antis == frozenset({9})
    assert n_k == (0, 3, 1)


def test_findings_from_an_empty_report_are_empty() -> None:
    assert findings_from_report(None) == (frozenset(), frozenset(), None)
    assert findings_from_report({}) == (frozenset(), frozenset(), None)


def test_assemble_scene_serves_disjoint_chunks_from_one_projection(
    healthy_adapter,
) -> None:
    assembled = assemble_scene(
        healthy_adapter, requested_budget=40, device_max_points=40
    )
    first = assembled.chunk(0)
    if assembled.plan().chunk_count > 1:
        second = assembled.chunk(1)
        overlap = {int(x) for x in first.ids} & {int(x) for x in second.ids}
        assert overlap == set()
    assert first.lod.actual_count <= 40
