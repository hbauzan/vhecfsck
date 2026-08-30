"""Unit tests for binary scene codec and transport (P4-04)."""

from __future__ import annotations

import json

import numpy as np
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload
from vhecfsck.report.scene_codec import (
    decode_scene_binary,
    encode_scene_binary,
    encode_scene_json,
)


def _make_sample_scene() -> ScenePayload:
    n = 20
    rng1 = np.random.default_rng(1)
    rng2 = np.random.default_rng(2)
    positions = rng1.uniform(-1.0, 1.0, size=(n, 3)).astype(np.float32)
    cls_list = [PointClass.HEALTHY.value, PointClass.HUB.value]
    classes = rng2.choice(cls_list, size=n).astype(np.uint8)
    ids = np.arange(n, dtype=np.int64)
    partition_id = np.ones(n, dtype=np.int32)
    nk = np.full(n, 5, dtype=np.int32)

    lod = LodMetadata(
        requested_budget=100,
        actual_count=n,
        decimation_method="none",
        complete=True,
        has_tombstones=False,
    )

    return ScenePayload(
        positions=positions,
        classes=classes,
        ids=ids,
        lod=lod,
        partition_id=partition_id,
        nk=nk,
    )


def test_scene_codec_binary_roundtrip() -> None:
    """Encode scene to binary octet-stream and decode back to identical payload."""
    original = _make_sample_scene()

    binary_data = encode_scene_binary(original)
    decoded = decode_scene_binary(binary_data)

    assert decoded.lod == original.lod
    assert np.array_equal(decoded.positions, original.positions)
    assert np.array_equal(decoded.classes, original.classes)
    assert np.array_equal(decoded.ids, original.ids)
    assert decoded.partition_id is not None and original.partition_id is not None
    assert np.array_equal(decoded.partition_id, original.partition_id)
    assert decoded.nk is not None and original.nk is not None
    assert np.array_equal(decoded.nk, original.nk)


def test_scene_codec_buffer_offsets_aligned_to_8_bytes() -> None:
    """All buffer offsets must be 8-byte aligned for typed arrays."""
    scene = _make_sample_scene()
    binary_data = encode_scene_binary(scene)

    header_len = int(np.frombuffer(binary_data[:4], dtype=np.uint32)[0])
    body_start_offset = 4 + header_len

    header_json = json.loads(binary_data[4:body_start_offset].decode("utf-8"))

    for field_info in header_json["buffers"].values():
        offset = field_info["offset"]
        abs_offset = body_start_offset + offset
        assert abs_offset % 8 == 0, f"Offset {abs_offset} is not 8-byte aligned"


def test_scene_codec_json_debug_format() -> None:
    """JSON debug renderer produces human-readable scene representation."""
    scene = _make_sample_scene()
    json_text = encode_scene_json(scene)

    parsed = json.loads(json_text)

    assert parsed["n_points"] == 20
    assert len(parsed["positions"]) == 20
    assert len(parsed["classes"]) == 20
    assert len(parsed["ids"]) == 20
