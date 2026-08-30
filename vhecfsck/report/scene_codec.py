"""Binary transport codec and JSON debug renderer for ScenePayload (P4-04)."""

from __future__ import annotations

import json
import struct
import sys

import numpy as np

from vhecfsck.models.scene import (
    DEFAULT_COLOR_PALETTE,
    LodMetadata,
    PointClass,
    ScenePayload,
)

msg_byteorder = "vhecfsck scene codec requires a little-endian host system"
assert sys.byteorder == "little", msg_byteorder


def encode_scene_binary(scene: ScenePayload) -> bytes:
    """Encode ScenePayload into application/octet-stream binary format.

    Layout:
        - 4 bytes uint32: header JSON length in bytes (little-endian)
        - N bytes: JSON header (metadata, legend, buffer offsets, dtypes, shapes)
        - M bytes: 8-byte aligned raw binary buffer payload

    Args:
        scene: ScenePayload instance to encode.

    Returns:
        Binary bytes blob ready for transport.
    """
    n_points = len(scene.positions)
    legend = {pc.name: color for pc, color in DEFAULT_COLOR_PALETTE.items()}

    buffers_dict: dict[str, dict[str, str | int | list[int]]] = {}
    packed_data_list: list[bytes] = []
    current_offset = 0

    fields_to_pack: list[tuple[str, np.ndarray, str]] = [
        ("positions", scene.positions.astype("<f4"), "float32"),
        ("classes", scene.classes.astype("u1"), "uint8"),
        ("ids", scene.ids.astype("<i8"), "int64"),
    ]

    if scene.partition_id is not None:
        part_arr = scene.partition_id.astype("<i4")
        fields_to_pack.append(("partition_id", part_arr, "int32"))
    if scene.nk is not None:
        nk_arr = scene.nk.astype("<i4")
        fields_to_pack.append(("nk", nk_arr, "int32"))

    for field_name, array, dtype_str in fields_to_pack:
        raw_bytes = array.tobytes()
        byte_len = len(raw_bytes)
        shape_list = list(array.shape)

        buffers_dict[field_name] = {
            "offset": current_offset,
            "byte_length": byte_len,
            "dtype": dtype_str,
            "shape": shape_list,
        }

        packed_data_list.append(raw_bytes)
        current_offset += byte_len

        padding = (8 - (current_offset % 8)) % 8
        if padding > 0:
            packed_data_list.append(b"\x00" * padding)
            current_offset += padding

    header_dict = {
        "n_points": n_points,
        "legend": legend,
        "lod": {
            "requested_budget": scene.lod.requested_budget,
            "actual_count": scene.lod.actual_count,
            "decimation_method": scene.lod.decimation_method,
            "complete": scene.lod.complete,
            "has_tombstones": scene.lod.has_tombstones,
        },
        "buffers": buffers_dict,
    }

    header_bytes = json.dumps(header_dict, separators=(",", ":")).encode("utf-8")

    header_padding = (8 - ((4 + len(header_bytes)) % 8)) % 8
    if header_padding > 0:
        header_bytes += b" " * header_padding

    header_len = len(header_bytes)
    prefix = struct.pack("<I", header_len)

    return prefix + header_bytes + b"".join(packed_data_list)


def decode_scene_binary(data: bytes) -> ScenePayload:
    """Decode application/octet-stream binary data back to a ScenePayload.

    Args:
        data: Encoded binary bytes blob.

    Returns:
        Reconstructed ScenePayload instance.
    """
    if len(data) < 4:
        raise ValueError("Binary scene payload too short")

    header_len = struct.unpack("<I", data[:4])[0]
    header_end = 4 + header_len
    if len(data) < header_end:
        raise ValueError("Truncated binary scene header")

    header_json = json.loads(data[4:header_end].decode("utf-8"))
    body_data = data[header_end:]

    lod_dict = header_json["lod"]
    lod = LodMetadata(
        requested_budget=lod_dict["requested_budget"],
        actual_count=lod_dict["actual_count"],
        decimation_method=lod_dict["decimation_method"],
        complete=lod_dict["complete"],
        has_tombstones=lod_dict["has_tombstones"],
    )

    buffers_info = header_json["buffers"]

    pos_info = buffers_info["positions"]
    p_off, p_len = pos_info["offset"], pos_info["byte_length"]
    positions = (
        np.frombuffer(body_data[p_off : p_off + p_len], dtype="<f4")
        .reshape(pos_info["shape"])
        .copy()
    )

    cls_info = buffers_info["classes"]
    c_off, c_len = cls_info["offset"], cls_info["byte_length"]
    classes = (
        np.frombuffer(body_data[c_off : c_off + c_len], dtype="u1")
        .reshape(cls_info["shape"])
        .copy()
    )

    ids_info = buffers_info["ids"]
    i_off, i_len = ids_info["offset"], ids_info["byte_length"]
    ids = (
        np.frombuffer(body_data[i_off : i_off + i_len], dtype="<i8")
        .reshape(ids_info["shape"])
        .copy()
    )

    part_id: np.ndarray | None = None
    if "partition_id" in buffers_info:
        p_info = buffers_info["partition_id"]
        pt_off, pt_len = p_info["offset"], p_info["byte_length"]
        pt_slice = body_data[pt_off : pt_off + pt_len]
        part_id = np.frombuffer(pt_slice, dtype="<i4").reshape(p_info["shape"]).copy()

    nk_arr: np.ndarray | None = None
    if "nk" in buffers_info:
        nk_info = buffers_info["nk"]
        nk_off, nk_len = nk_info["offset"], nk_info["byte_length"]
        nk_slice = body_data[nk_off : nk_off + nk_len]
        nk_arr = np.frombuffer(nk_slice, dtype="<i4").reshape(nk_info["shape"]).copy()

    return ScenePayload(
        positions=positions,
        classes=classes,
        ids=ids,
        lod=lod,
        partition_id=part_id,
        nk=nk_arr,
    )


def encode_scene_json(scene: ScenePayload) -> str:
    """Encode ScenePayload into human-readable JSON debug representation.

    Args:
        scene: ScenePayload instance to encode.

    Returns:
        JSON text representation suitable for human inspection.
    """
    legend = {pc.name: color for pc, color in DEFAULT_COLOR_PALETTE.items()}
    class_names = [PointClass(int(c)).name for c in scene.classes]

    data = {
        "n_points": len(scene.positions),
        "legend": legend,
        "lod": {
            "requested_budget": scene.lod.requested_budget,
            "actual_count": scene.lod.actual_count,
            "decimation_method": scene.lod.decimation_method,
            "complete": scene.lod.complete,
            "has_tombstones": scene.lod.has_tombstones,
        },
        "positions": scene.positions.tolist(),
        "classes": class_names,
        "ids": scene.ids.tolist(),
    }

    if scene.partition_id is not None:
        data["partition_id"] = scene.partition_id.tolist()
    if scene.nk is not None:
        data["nk"] = scene.nk.tolist()

    return json.dumps(data, indent=2)
