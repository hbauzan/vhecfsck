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
from vhecfsck.core.camera import (
    ANTIHUB_PERIPHERY,
    HUB_CLUSTER,
    OVERVIEW,
    WORST_PARTITION,
    build_tour,
    derive_presets,
    sample_tour,
)
from vhecfsck.models.scene import (
    DEFAULT_COLOR_PALETTE,
    LodMetadata,
    PointClass,
    ScenePayload,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GIF = ROOT / "docs" / "assets" / "vhecfsck-demo.gif"
DEFAULT_PNG = ROOT / "docs" / "assets" / "vhecfsck-demo.png"
DEFAULT_MP4 = ROOT / "docs" / "assets" / "vhecfsck-demo.mp4"
SEED = 4
WIDTH = 640
HEIGHT = 360

# 5x7 pixel font for UI text rendering
FONT_5X7: dict[str, tuple[int, ...]] = {
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x13, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x1F, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    ".": (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C),
    ":": (0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00),
    "-": (0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00),
    "+": (0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00),
    "(": (0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02),
    ")": (0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08),
    "[": (0x0E, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0E),
    "]": (0x0E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0E),
    "<": (0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02),
    ">": (0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08),
    "%": (0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13),
    "/": (0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00),
    "=": (0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00, 0x00),
    " ": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
}


def _draw_rect(
    img: NDArray[np.uint8],
    x: int,
    y: int,
    w: int,
    h: int,
    color: tuple[int, int, int],
) -> None:
    h_img, w_img, _ = img.shape
    x1, x2 = max(0, x), min(w_img, x + w)
    y1, y2 = max(0, y), min(h_img, y + h)
    if x1 < x2 and y1 < y2:
        img[y1:y2, x1:x2] = color


def _draw_box(
    img: NDArray[np.uint8],
    x: int,
    y: int,
    w: int,
    h: int,
    bg_color: tuple[int, int, int],
    border_color: tuple[int, int, int] | None = None,
) -> None:
    _draw_rect(img, x, y, w, h, bg_color)
    if border_color is not None:
        _draw_rect(img, x, y, w, 1, border_color)
        _draw_rect(img, x, y + h - 1, w, 1, border_color)
        _draw_rect(img, x, y, 1, h, border_color)
        _draw_rect(img, x + w - 1, y, 1, h, border_color)


def _draw_text(
    img: NDArray[np.uint8],
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    scale: int = 1,
) -> None:
    h_img, w_img, _ = img.shape
    cur_x = x
    for ch in text:
        key = ch.upper() if ch.upper() in FONT_5X7 else " "
        rows = FONT_5X7.get(key, FONT_5X7[" "])
        for r, row_bits in enumerate(rows):
            for c in range(5):
                if (row_bits >> (4 - c)) & 1:
                    px = cur_x + c * scale
                    py = y + r * scale
                    if 0 <= px < w_img and 0 <= py < h_img:
                        if scale == 1:
                            img[py, px] = color
                        else:
                            _draw_rect(img, px, py, scale, scale, color)
        cur_x += 6 * scale


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
    preset: str = OVERVIEW,
    caption: str = "",
) -> NDArray[np.uint8]:
    """Splat the scene from ``eye`` looking at ``target`` into an RGB image with WebGUI HUD."""
    projected = _look_at(
        scene.positions,
        np.asarray(eye, dtype=np.float64),
        np.asarray(target, dtype=np.float64),
    )
    # Dark background matching WebGUI --bg-dark (#0f1117)
    img = np.full((height, width, 3), 15, dtype=np.uint8)
    img[:, :, 1] = 17
    img[:, :, 2] = 23

    # If canvas is wide enough, offset 3D scene center to the right
    hud_w = min(220, int(width * 0.35)) if width >= 300 and height >= 160 else 0
    cx = (width + hud_w) / 2.0 if hud_w > 0 else width / 2.0
    cy = (height - 30) / 2.0 if hud_w > 0 else height / 2.0
    scale_factor = min(width - hud_w, height) * 0.45

    xs = (cx + projected[:, 0] * scale_factor).astype(np.int32)
    ys = (cy - projected[:, 1] * scale_factor).astype(np.int32)
    order = np.argsort(-projected[:, 2])
    palette = DEFAULT_COLOR_PALETTE

    # Render 3D point cloud
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

    # Draw full WebGUI overlay HUD cards if canvas is sufficiently large
    if hud_w >= 140 and height >= 160:
        hud_h = height - 44
        # Main HUD card container (#161a24 bg, #2d3748 border)
        _draw_box(
            img,
            12,
            12,
            hud_w,
            hud_h,
            bg_color=(22, 26, 36),
            border_color=(45, 55, 72),
        )

        # Header title
        _draw_text(img, "VHECFSCK AUDIT", 22, 22, color=(226, 232, 240), scale=1)

        # Verdict Badge [FAIL] (red #ef4444)
        badge_x = 12 + hud_w - 42
        _draw_box(
            img,
            badge_x,
            20,
            34,
            14,
            bg_color=(239, 68, 68),
            border_color=(220, 38, 38),
        )
        _draw_text(img, "FAIL", badge_x + 5, 24, color=(255, 255, 255), scale=1)

        # Separator line
        _draw_rect(img, 22, 40, hud_w - 20, 1, color=(45, 55, 72))

        # Caveat alert box (amber border)
        _draw_box(
            img,
            20,
            46,
            hud_w - 16,
            24,
            bg_color=(30, 41, 59),
            border_color=(245, 158, 11),
        )
        _draw_text(
            img,
            "3D SKETCH (PCA)",
            26,
            50,
            color=(245, 158, 11),
            scale=1,
        )
        _draw_text(
            img,
            "LOSSY HIGH-D",
            26,
            59,
            color=(148, 163, 184),
            scale=1,
        )

        # Audit Metrics Section
        _draw_text(img, "AUDIT METRICS", 22, 76, color=(148, 163, 184), scale=1)

        metrics = [
            ("CANARY RECALL", "0.6815 RATIO", True),
            ("HUB SHARE TOP1", "0.0548 RATIO", False),
            ("ANTIHUB FRAC", "0.0506 RATIO", False),
            ("DFI", "0.3500 RATIO", True),
        ]

        my = 88
        for title, val, is_fail in metrics:
            if my + 26 > 12 + hud_h:
                break
            b_color = (239, 68, 68) if is_fail else (45, 55, 72)
            _draw_box(
                img,
                20,
                my,
                hud_w - 16,
                22,
                bg_color=(28, 33, 46),
                border_color=b_color,
            )
            _draw_text(img, title, 25, my + 3, color=(148, 163, 184), scale=1)
            _draw_text(
                img,
                val,
                25,
                my + 12,
                color=(239, 68, 68) if is_fail else (226, 232, 240),
                scale=1,
            )
            my += 26

        # Selectors (COLOUR BY / PALETTE)
        if my + 32 <= 12 + hud_h:
            _draw_text(img, "COLOUR BY", 22, my + 4, color=(148, 163, 184))
            _draw_box(
                img,
                20,
                my + 14,
                hud_w - 16,
                16,
                bg_color=(30, 41, 59),
                border_color=(45, 55, 72),
            )
            _draw_text(img, "CLASS", 26, my + 18, color=(226, 232, 240), scale=1)

        # Bottom Controls Bar
        bar_y = height - 28
        bar_x = 12
        bar_w = width - 24
        _draw_box(
            img,
            bar_x,
            bar_y,
            bar_w,
            20,
            bg_color=(22, 26, 36),
            border_color=(45, 55, 72),
        )

        buttons = [
            ("RESET", False),
            ("OVERVIEW", preset == OVERVIEW),
            ("HUBS", preset == HUB_CLUSTER),
            ("ANTI-HUBS", preset == ANTIHUB_PERIPHERY),
            ("WORST CELL", preset == WORST_PARTITION),
        ]

        bx = bar_x + 6
        for btn_name, active in buttons:
            bw = len(btn_name) * 6 + 10
            if bx + bw > bar_x + bar_w - 6:
                break
            bg = (59, 130, 246) if active else (30, 41, 59)
            border = (147, 197, 253) if active else (51, 65, 85)
            tc = (255, 255, 255) if active else (148, 163, 184)
            _draw_box(
                img,
                bx,
                bar_y + 3,
                bw,
                14,
                bg_color=bg,
                border_color=border,
            )
            _draw_text(img, btn_name, bx + 5, bar_y + 6, color=tc, scale=1)
            bx += bw + 6

    # Render Preset Caption Banner at top right canvas area
    if caption and width >= 360 and height >= 160:
        cap_str = caption.upper()
        cap_w = len(cap_str) * 6 + 16
        cap_x = int(cx - cap_w / 2)
        _draw_box(
            img,
            cap_x,
            12,
            cap_w,
            18,
            bg_color=(22, 26, 36),
            border_color=(59, 130, 246),
        )
        _draw_text(
            img,
            cap_str,
            cap_x + 8,
            17,
            color=(59, 130, 246),
            scale=1,
        )

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
    unique, counts = np.unique(stacked, axis=0, return_counts=True)
    if len(unique) <= colours:
        palette = unique.astype(np.int16)
    else:
        top_indices = np.argsort(-counts)[:colours]
        palette = unique[top_indices].astype(np.int16)
    while len(palette) < colours:
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


def write_png(frame: NDArray[np.uint8], path: Path) -> None:
    """Write an RGB numpy image to PNG using stdlib zlib."""
    import struct
    import zlib

    h, w, _ = frame.shape
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(frame[y].tobytes())
    compressed = zlib.compress(bytes(raw), level=9)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", compressed)
    iend = _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + ihdr + idat + iend)


def capture(
    path: Path = DEFAULT_GIF,
    *,
    fps: int = 8,
    width: int = WIDTH,
    height: int = HEIGHT,
    png_path: Path = DEFAULT_PNG,
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
                preset=tour_frame.preset,
                caption=tour_frame.caption,
            )
        )
    write_gif(frames, path)
    if frames:
        write_png(frames[0], png_path)
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
