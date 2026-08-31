"""Deterministic README demo capture (P6-07).

Renders the scripted tour of a golden scene to an animated GIF (and MP4
when ffmpeg is on PATH). Two runs with the same seed produce identical
bytes — that is the whole point of sampling the tour off a wall clock.
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from vhecfsck.core.camera import build_tour, derive_presets, sample_tour
from vhecfsck.models.scene import (
    DEFAULT_COLOR_PALETTE,
    LodMetadata,
    PointClass,
    ScenePayload,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GIF = ROOT / "docs" / "assets" / "vhecfsck-demo.gif"
DEFAULT_MP4 = ROOT / "docs" / "assets" / "vhecfsck-demo.mp4"
SEED = 4
WIDTH = 320
HEIGHT = 180


def golden_scene() -> ScenePayload:
    """Fixed scene standing in for a golden report (healthy → hubs → anti-hubs)."""
    rng = np.random.default_rng(SEED)
    n = 240
    positions = rng.uniform(-0.8, 0.8, size=(n, 3)).astype(np.float32)
    classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
    positions[0:12] = np.array([0.35, 0.35, 0.2], dtype=np.float32)
    positions[0:12] += rng.normal(scale=0.03, size=(12, 3)).astype(np.float32)
    classes[0:12] = PointClass.HUB.value
    positions[12:22] = np.array([-0.75, -0.65, 0.1], dtype=np.float32)
    classes[12:22] = PointClass.ANTIHUB.value
    partition = np.zeros(n, dtype=np.int32)
    partition[:160] = 2
    partition[160:210] = 1
    partition[210:] = 0
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


def _look_at(
    positions: NDArray[np.float32],
    eye: NDArray[np.float64],
    target: NDArray[np.float64],
) -> NDArray[np.float32]:
    forward = target - eye
    norm = float(np.sqrt(float(forward @ forward))) or 1.0
    forward = forward / norm
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up)
    rnorm = float(np.sqrt(float(right @ right))) or 1.0
    right = right / rnorm
    up = np.cross(right, forward)
    rel = positions.astype(np.float64) - eye
    x = rel @ right
    y = rel @ up
    z = rel @ forward
    z = np.clip(z, 0.15, None)
    return np.column_stack((x / z, y / z, z)).astype(np.float32)


def render_frame(
    scene: ScenePayload,
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> NDArray[np.uint8]:
    """Splat the scene from ``eye`` looking at ``target`` into an RGB image."""
    projected = _look_at(
        scene.positions,
        np.asarray(eye, dtype=np.float64),
        np.asarray(target, dtype=np.float64),
    )
    img = np.full((height, width, 3), 15, dtype=np.uint8)
    img[:, :, 1] = 17
    img[:, :, 2] = 23
    xs = ((projected[:, 0] * 0.45 + 0.5) * (width - 1)).astype(np.int32)
    ys = ((0.5 - projected[:, 1] * 0.45) * (height - 1)).astype(np.int32)
    order = np.argsort(-projected[:, 2])
    palette = DEFAULT_COLOR_PALETTE
    for idx in order:
        x = int(xs[idx])
        y = int(ys[idx])
        if x < 1 or y < 1 or x >= width - 1 or y >= height - 1:
            continue
        cls = PointClass(int(scene.classes[idx]))
        hex_colour = palette[cls].lstrip("#")
        rgb = (
            int(hex_colour[0:2], 16),
            int(hex_colour[2:4], 16),
            int(hex_colour[4:6], 16),
        )
        radius = 2 if cls is PointClass.HEALTHY else 3
        img[y - radius : y + radius + 1, x - radius : x + radius + 1] = rgb
    return img


def _lzw_encode(indexes: bytes, min_code_size: int) -> bytes:
    clear = 1 << min_code_size
    eoi = clear + 1
    next_code = eoi + 1
    code_size = min_code_size + 1
    table: dict[bytes, int] = {bytes([i]): i for i in range(clear)}
    buf = 0
    nbits = 0
    out = bytearray()

    def emit(code: int) -> None:
        nonlocal buf, nbits, code_size
        buf |= code << nbits
        nbits += code_size
        while nbits >= 8:
            out.append(buf & 0xFF)
            buf >>= 8
            nbits -= 8

    emit(clear)
    w = bytes([indexes[0]])
    for byte in indexes[1:]:
        nxt = w + bytes([byte])
        if nxt in table:
            w = nxt
            continue
        emit(table[w])
        if next_code < 4096:
            table[nxt] = next_code
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
            next_code += 1
        else:
            emit(clear)
            table = {bytes([i]): i for i in range(clear)}
            next_code = eoi + 1
            code_size = min_code_size + 1
        w = bytes([byte])
    emit(table[w])
    emit(eoi)
    if nbits:
        out.append(buf & 0xFF)
    return bytes(out)


def _palette_from_frames(
    frames: list[NDArray[np.uint8]], colours: int = 32
) -> NDArray[np.int16]:
    stacked = np.concatenate([f.reshape(-1, 3) for f in frames], axis=0)
    rows = [stacked[0]]
    stride = max(1, stacked.shape[0] // colours)
    for i in range(0, stacked.shape[0], stride):
        if len(rows) >= colours:
            break
        rows.append(stacked[i])
    palette = np.vstack(rows).astype(np.int16)
    while palette.shape[0] < colours:
        palette = np.vstack([palette, palette[-1]])
    return palette[:colours]


def _index_frame(frame: NDArray[np.uint8], palette: NDArray[np.int16]) -> bytes:
    flat = frame.reshape(-1, 3).astype(np.int16)
    deltas = flat[:, None, :] - palette[None, :, :]
    dist = np.sum(deltas * deltas, axis=2)
    return bytes(np.argmin(dist, axis=1).astype(np.uint8).tolist())


def write_gif(
    frames: list[NDArray[np.uint8]], path: Path, *, delay_cs: int = 12
) -> None:
    """Write an animated GIF from RGB frames."""
    if not frames:
        msg = "no frames to encode"
        raise ValueError(msg)
    height, width, _ = frames[0].shape
    palette = _palette_from_frames(frames)
    pal_bytes = bytes(int(v) for row in palette for v in row)
    min_code = 8
    header = b"GIF89a" + struct.pack("<HH", width, height) + bytes([0xF7, 0, 0])
    header += pal_bytes + b"\x00" * (768 - len(pal_bytes))
    ext = b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    body = bytearray(header + ext)
    for frame in frames:
        indexes = _index_frame(frame, palette)
        body.extend(b"\x21\xf9\x04\x04" + struct.pack("<H", delay_cs) + b"\x00\x00")
        body.extend(b"\x2c" + struct.pack("<HHHH", 0, 0, width, height) + b"\x00")
        encoded = _lzw_encode(indexes, min_code)
        body.append(min_code)
        for offset in range(0, len(encoded), 255):
            chunk = encoded[offset : offset + 255]
            body.append(len(chunk))
            body.extend(chunk)
        body.append(0)
    body.append(0x3B)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(body))


def capture(
    path: Path = DEFAULT_GIF,
    *,
    fps: int = 8,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> Path:
    """Render the tour and write ``path``."""
    scene = golden_scene()
    presets = derive_presets(scene)
    timeline = build_tour(presets, fps=fps, transition_seconds=0.5, hold_seconds=0.75)
    frames = []
    for tour_frame in sample_tour(timeline, presets):
        frames.append(
            render_frame(
                scene,
                tour_frame.position,
                tour_frame.target,
                width=width,
                height=height,
            )
        )
    write_gif(frames, path)
    return path


def maybe_encode_mp4(gif_path: Path, mp4_path: Path = DEFAULT_MP4) -> Path | None:
    """Encode MP4 with ffmpeg when available; otherwise return None."""
    ffmpeg = _which_ffmpeg()
    if ffmpeg is None:
        return None
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(gif_path),
            "-movflags",
            "faststart",
            "-pix_fmt",
            "yuv420p",
            str(mp4_path),
        ],
        check=True,
        capture_output=True,
    )
    return mp4_path


def _which_ffmpeg() -> str | None:
    from shutil import which

    return which("ffmpeg")


def main(argv: list[str] | None = None) -> int:
    """CLI entry: write the README GIF next to an optional MP4."""
    _ = argv
    gif = capture()
    mp4 = maybe_encode_mp4(gif)
    sys.stderr.write(f"wrote {gif}\n")
    if mp4 is not None:
        sys.stderr.write(f"wrote {mp4}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
