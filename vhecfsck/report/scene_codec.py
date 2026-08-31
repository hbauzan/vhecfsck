"""Binary transport codec and JSON debug renderer for ScenePayload.

P4-04 defined the container. P6 widened the header so the browser receives
everything it needs already computed: every palette, the marker and size
channels that keep class legible without hue, chunk position in a progressive
stream, and the tombstone layer's verdict. The client selects and renders; it
derives nothing.
"""

from __future__ import annotations

import json
import struct
import sys

import numpy as np

from vhecfsck.models.scene import (
    CLASS_MARKERS,
    CLASS_SIZE_SCALE,
    DEFAULT_PALETTE_NAME,
    PALETTES,
    LodMetadata,
    PointClass,
    ScenePayload,
    resolve_palette,
)

msg_byteorder = "vhecfsck scene codec requires a little-endian host system"
assert sys.byteorder == "little", msg_byteorder


def _theme_header(palette: str) -> dict[str, object]:
    """Palette, marker and size channels for the active theme."""
    active = resolve_palette(palette)
    return {
        "palette": palette,
        "legend": {pc.name: colour for pc, colour in active.items()},
        "palettes": {
            name: {pc.name: colour for pc, colour in table.items()}
            for name, table in PALETTES.items()
        },
        "markers": {pc.name: int(marker) for pc, marker in CLASS_MARKERS.items()},
        "size_scale": {pc.name: scale for pc, scale in CLASS_SIZE_SCALE.items()},
    }


def _lod_header(lod: LodMetadata) -> dict[str, object]:
    return {
        "requested_budget": lod.requested_budget,
        "actual_count": lod.actual_count,
        "decimation_method": lod.decimation_method,
        "complete": lod.complete,
        "has_tombstones": lod.has_tombstones,
        "chunk_index": lod.chunk_index,
        "chunk_count": lod.chunk_count,
        "total_available": lod.total_available,
        "tombstone_count": lod.tombstone_count,
        "tombstone_reason": lod.tombstone_reason,
    }


def _as_int(value: object) -> int:
    """Coerce a JSON header field to int without silencing mypy."""
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value)
        msg = f"lod header field is not int-compatible: {type(value).__name__}"
        raise TypeError(msg)
    return value


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _as_int(value)


def _lod_from_header(raw: dict[str, object]) -> LodMetadata:
    return LodMetadata(
        requested_budget=_as_int(raw["requested_budget"]),
        actual_count=_as_int(raw["actual_count"]),
        decimation_method=str(raw["decimation_method"]),
        complete=bool(raw["complete"]),
        has_tombstones=bool(raw["has_tombstones"]),
        chunk_index=_as_int(raw.get("chunk_index", 0)),
        chunk_count=_as_int(raw.get("chunk_count", 1)),
        total_available=_as_optional_int(raw.get("total_available")),
        tombstone_count=_as_optional_int(raw.get("tombstone_count")),
        tombstone_reason=(
            None
            if raw.get("tombstone_reason") is None
            else str(raw["tombstone_reason"])
        ),
    )


def encode_scene_binary(
    scene: ScenePayload,
    *,
    palette: str = DEFAULT_PALETTE_NAME,
) -> bytes:
    """Encode ScenePayload into application/octet-stream binary format.

    Layout:
        - 4 bytes uint32: header JSON length in bytes (little-endian)
        - N bytes: JSON header (metadata, theme, buffer offsets, dtypes, shapes)
        - M bytes: 8-byte aligned raw binary buffer payload

    Args:
        scene: ScenePayload instance to encode.
        palette: Name of the palette to mark active in the header.

    Returns:
        Binary bytes blob ready for transport.
    """
    n_points = len(scene.positions)

    buffers_dict: dict[str, dict[str, str | int | list[int]]] = {}
    packed_data_list: list[bytes] = []
    current_offset = 0

    fields_to_pack: list[tuple[str, np.ndarray, str]] = [
        ("positions", scene.positions.astype("<f4"), "float32"),
        ("classes", scene.classes.astype("u1"), "uint8"),
        ("ids", scene.ids.astype("<i8"), "int64"),
    ]

    if scene.partition_id is not None:
        fields_to_pack.append(
            ("partition_id", scene.partition_id.astype("<i4"), "int32")
        )
    if scene.nk is not None:
        fields_to_pack.append(("nk", scene.nk.astype("<i4"), "int32"))
    if scene.dist_centroid is not None:
        fields_to_pack.append(
            ("dist_centroid", scene.dist_centroid.astype("<f4"), "float32")
        )

    for field_name, array, dtype_str in fields_to_pack:
        raw_bytes = array.tobytes()
        byte_len = len(raw_bytes)

        buffers_dict[field_name] = {
            "offset": current_offset,
            "byte_length": byte_len,
            "dtype": dtype_str,
            "shape": list(array.shape),
        }

        packed_data_list.append(raw_bytes)
        current_offset += byte_len

        padding = (8 - (current_offset % 8)) % 8
        if padding > 0:
            packed_data_list.append(b"\x00" * padding)
            current_offset += padding

    header_dict: dict[str, object] = {
        "n_points": n_points,
        "lod": _lod_header(scene.lod),
        "buffers": buffers_dict,
    }
    header_dict.update(_theme_header(palette))

    header_bytes = json.dumps(header_dict, separators=(",", ":")).encode("utf-8")

    header_padding = (8 - ((4 + len(header_bytes)) % 8)) % 8
    if header_padding > 0:
        header_bytes += b" " * header_padding

    prefix = struct.pack("<I", len(header_bytes))

    return prefix + header_bytes + b"".join(packed_data_list)


def decode_scene_binary(data: bytes) -> ScenePayload:
    """Decode application/octet-stream binary data back to a ScenePayload.

    Args:
        data: Encoded binary bytes blob.

    Returns:
        Reconstructed ScenePayload instance.

    Raises:
        ValueError: If the blob is truncated.
    """
    if len(data) < 4:
        raise ValueError("Binary scene payload too short")

    header_len = struct.unpack("<I", data[:4])[0]
    header_end = 4 + header_len
    if len(data) < header_end:
        raise ValueError("Truncated binary scene header")

    header_json = json.loads(data[4:header_end].decode("utf-8"))
    body_data = data[header_end:]
    buffers_info = header_json["buffers"]

    def _read(name: str, dtype: str) -> np.ndarray:
        info = buffers_info[name]
        offset, length = info["offset"], info["byte_length"]
        chunk = body_data[offset : offset + length]
        return np.frombuffer(chunk, dtype=dtype).reshape(info["shape"]).copy()

    def _read_optional(name: str, dtype: str) -> np.ndarray | None:
        return _read(name, dtype) if name in buffers_info else None

    return ScenePayload(
        positions=_read("positions", "<f4"),
        classes=_read("classes", "u1"),
        ids=_read("ids", "<i8"),
        lod=_lod_from_header(header_json["lod"]),
        partition_id=_read_optional("partition_id", "<i4"),
        nk=_read_optional("nk", "<i4"),
        dist_centroid=_read_optional("dist_centroid", "<f4"),
    )


def encode_scene_json(
    scene: ScenePayload,
    *,
    palette: str = DEFAULT_PALETTE_NAME,
) -> str:
    """Encode ScenePayload into human-readable JSON debug representation.

    Args:
        scene: ScenePayload instance to encode.
        palette: Name of the palette to mark active.

    Returns:
        JSON text representation suitable for human inspection.
    """
    data: dict[str, object] = {
        "n_points": len(scene.positions),
        "lod": _lod_header(scene.lod),
        "positions": scene.positions.tolist(),
        "classes": [PointClass(int(c)).name for c in scene.classes],
        "ids": scene.ids.tolist(),
    }
    data.update(_theme_header(palette))

    if scene.partition_id is not None:
        data["partition_id"] = scene.partition_id.tolist()
    if scene.nk is not None:
        data["nk"] = scene.nk.tolist()
    if scene.dist_centroid is not None:
        data["dist_centroid"] = scene.dist_centroid.tolist()

    return json.dumps(data, indent=2)
