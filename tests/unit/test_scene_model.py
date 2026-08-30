"""Unit tests for scene payload model (P4-02)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.models.scene import (
    DEFAULT_COLOR_PALETTE,
    LodMetadata,
    PointClass,
    ScenePayload,
)


def test_point_class_enum_values() -> None:
    """Verify PointClass contains all 8 required variants for P4 and P6."""
    expected = {
        "HEALTHY",
        "HUB",
        "ANTIHUB",
        "TOMBSTONE",
        "QUERY",
        "TRUE_NEIGHBOUR",
        "RETURNED",
        "MISSED",
    }
    assert {pc.name for pc in PointClass} == expected


def test_color_palette_mapping_completeness() -> None:
    """DEFAULT_COLOR_PALETTE defines color for every PointClass variant."""
    for point_class in PointClass:
        assert point_class in DEFAULT_COLOR_PALETTE
        color_hex = DEFAULT_COLOR_PALETTE[point_class]
        assert color_hex.startswith("#")
        assert len(color_hex) == 7


def test_scene_payload_valid_creation() -> None:
    """ScenePayload validates arrays and attributes correctly."""
    n = 10
    positions = np.zeros((n, 3), dtype=np.float32)
    classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
    ids = np.arange(n, dtype=np.int64)

    lod = LodMetadata(
        requested_budget=100,
        actual_count=n,
        decimation_method="none",
        complete=True,
        has_tombstones=False,
    )

    payload = ScenePayload(
        positions=positions,
        classes=classes,
        ids=ids,
        lod=lod,
    )

    assert payload.positions.shape == (10, 3)
    assert payload.classes.shape == (10,)
    assert payload.ids.shape == (10,)
    assert payload.lod.complete is True


def test_scene_payload_mismatched_array_lengths_raises() -> None:
    """Mismatched field lengths between positions, classes, and ids raise ValueError."""
    positions = np.zeros((10, 3), dtype=np.float32)
    classes = np.zeros(8, dtype=np.uint8)  # length 8 != 10
    ids = np.arange(10, dtype=np.int64)

    lod = LodMetadata(
        requested_budget=100,
        actual_count=10,
        decimation_method="none",
        complete=True,
        has_tombstones=False,
    )

    with pytest.raises(ValueError, match="Length mismatch"):
        ScenePayload(
            positions=positions,
            classes=classes,
            ids=ids,
            lod=lod,
        )


def test_scene_payload_optional_nk_and_partition() -> None:
    """Optional partition_id and nk arrays must match scene size if provided."""
    n = 5
    positions = np.zeros((n, 3), dtype=np.float32)
    classes = np.zeros(n, dtype=np.uint8)
    ids = np.arange(n, dtype=np.int64)
    partition_id = np.ones(n, dtype=np.int32)
    nk = np.full(n, 10, dtype=np.int32)

    lod = LodMetadata(
        requested_budget=10,
        actual_count=n,
        decimation_method="none",
        complete=True,
        has_tombstones=False,
    )

    payload = ScenePayload(
        positions=positions,
        classes=classes,
        ids=ids,
        partition_id=partition_id,
        nk=nk,
        lod=lod,
    )

    assert payload.partition_id is not None
    assert payload.nk is not None
    assert len(payload.partition_id) == n
    assert len(payload.nk) == n
