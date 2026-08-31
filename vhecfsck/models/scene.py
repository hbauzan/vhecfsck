"""Domain models for 3D visualization scene payloads and Level-of-Detail metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


class PointClass(IntEnum):
    """Classification of vectors for visualization styling and legend mapping.

    Values:
        HEALTHY: Standard healthy vector embedding.
        HUB: High in-degree topology hub anomaly.
        ANTIHUB: Low in-degree isolated vector anomaly.
        TOMBSTONE: Soft-deleted or inactive vector.
        QUERY: Probe query vector.
        TRUE_NEIGHBOUR: Exact ground-truth neighbour.
        RETURNED: Vector returned by approximate search.
        MISSED: True neighbour missed by approximate search.
    """

    HEALTHY = 0
    HUB = 1
    ANTIHUB = 2
    TOMBSTONE = 3
    QUERY = 4
    TRUE_NEIGHBOUR = 5
    RETURNED = 6
    MISSED = 7


class PointMarker(IntEnum):
    """Marker shape drawn for a point class.

    Shape is the redundant channel that keeps class legible when hue is not
    (P6-08). Every class must map to a distinct marker.
    """

    DOT = 0
    DISC = 1
    RING = 2
    SQUARE = 3
    CROSS = 4
    DIAMOND = 5
    TRIANGLE = 6
    X_MARK = 7


class ColourBy(IntEnum):
    """Attribute driving point colour in the visualizer (P6-04)."""

    CLASS = 0
    PARTITION = 1
    NK = 2
    DISTANCE_TO_CENTROID = 3


DEFAULT_COLOR_PALETTE: dict[PointClass, str] = {
    PointClass.HEALTHY: "#808080",
    PointClass.HUB: "#FF4D4D",
    PointClass.ANTIHUB: "#4D79FF",
    PointClass.TOMBSTONE: "#4A4A4A",
    PointClass.QUERY: "#FFD700",
    PointClass.TRUE_NEIGHBOUR: "#00FF7F",
    PointClass.RETURNED: "#00BFFF",
    PointClass.MISSED: "#FF1493",
}

#: Deuteranopia-safe alternative (P6-08). Built from the Okabe-Ito set, which
#: is designed so no two entries collapse under red-green colour vision
#: deficiency. HUB and ANTIHUB are additionally separated in luminance so the
#: central finding survives a greyscale render.
DEUTERANOPIA_COLOR_PALETTE: dict[PointClass, str] = {
    PointClass.HEALTHY: "#9A9A9A",
    PointClass.HUB: "#D55E00",
    PointClass.ANTIHUB: "#56B4E9",
    PointClass.TOMBSTONE: "#3F3F3F",
    PointClass.QUERY: "#F0E442",
    PointClass.TRUE_NEIGHBOUR: "#009E73",
    PointClass.RETURNED: "#0072B2",
    PointClass.MISSED: "#CC79A7",
}

PALETTES: dict[str, dict[PointClass, str]] = {
    "default": DEFAULT_COLOR_PALETTE,
    "deuteranopia": DEUTERANOPIA_COLOR_PALETTE,
}

DEFAULT_PALETTE_NAME = "default"

#: Marker per class — the non-hue channel carrying identity (P6-08).
CLASS_MARKERS: dict[PointClass, PointMarker] = {
    PointClass.HEALTHY: PointMarker.DOT,
    PointClass.HUB: PointMarker.DISC,
    PointClass.ANTIHUB: PointMarker.RING,
    PointClass.TOMBSTONE: PointMarker.SQUARE,
    PointClass.QUERY: PointMarker.CROSS,
    PointClass.TRUE_NEIGHBOUR: PointMarker.DIAMOND,
    PointClass.RETURNED: PointMarker.TRIANGLE,
    PointClass.MISSED: PointMarker.X_MARK,
}

#: Size multiplier per class — the second non-hue channel (P6-08).
CLASS_SIZE_SCALE: dict[PointClass, float] = {
    PointClass.HEALTHY: 1.0,
    PointClass.HUB: 2.2,
    PointClass.ANTIHUB: 1.8,
    PointClass.TOMBSTONE: 1.4,
    PointClass.QUERY: 2.4,
    PointClass.TRUE_NEIGHBOUR: 1.9,
    PointClass.RETURNED: 1.6,
    PointClass.MISSED: 2.1,
}


def relative_luminance(hex_colour: str) -> float:
    """WCAG 2.1 relative luminance of an ``#rrggbb`` colour.

    Args:
        hex_colour: Colour as ``#rrggbb`` or ``rrggbb``.

    Returns:
        Relative luminance in ``[0, 1]``.

    Raises:
        ValueError: If the string is not six hexadecimal digits.
    """
    raw = hex_colour.lstrip("#")
    if len(raw) != 6:
        msg = f"expected #rrggbb, got {hex_colour!r}"
        raise ValueError(msg)

    channels: list[float] = []
    for offset in (0, 2, 4):
        srgb = int(raw[offset : offset + 2], 16) / 255.0
        linear = srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4
        channels.append(linear)

    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours.

    Args:
        first: First colour.
        second: Second colour.

    Returns:
        Ratio in ``[1, 21]``; higher means more separable, including in
        greyscale.
    """
    a = relative_luminance(first)
    b = relative_luminance(second)
    lighter, darker = (a, b) if a >= b else (b, a)
    return (lighter + 0.05) / (darker + 0.05)


def resolve_palette(name: str) -> dict[PointClass, str]:
    """Look up a palette by name.

    Args:
        name: Palette key, e.g. ``"default"`` or ``"deuteranopia"``.

    Returns:
        Mapping from class to ``#rrggbb``.

    Raises:
        KeyError: If the palette is unknown.
    """
    try:
        return PALETTES[name]
    except KeyError:
        known = ", ".join(sorted(PALETTES))
        msg = f"unknown palette {name!r}; known palettes: {known}"
        raise KeyError(msg) from None


@dataclass(frozen=True)
class LodMetadata:
    """Level-of-detail sampling metadata for scene payloads.

    Attributes:
        requested_budget: Target point count requested by client.
        actual_count: Number of points included in the payload.
        decimation_method: Description of sampling method applied.
        complete: True when the payload is the final one for this budget.
        has_tombstones: True if adapter provided tombstoned vector positions.
        chunk_index: Zero-based index of this chunk in a progressive stream.
        chunk_count: Total number of chunks the budget was split into.
        total_available: Live points available before decimation, if known.
        tombstone_count: Deleted vectors reported by the adapter, if known.
        tombstone_reason: Why tombstone positions are absent, when they are.
    """

    requested_budget: int
    actual_count: int
    decimation_method: str
    complete: bool
    has_tombstones: bool
    chunk_index: int = 0
    chunk_count: int = 1
    total_available: int | None = None
    tombstone_count: int | None = None
    tombstone_reason: str | None = None


@dataclass(frozen=True)
class ScenePayload:
    """Structured 3D scene payload passed to front-end renderer.

    Attributes:
        positions: Array of shape (N, 3) in float32 display cube [-1, 1]^3.
        classes: Array of shape (N,) in uint8 representing PointClass values.
        ids: Array of shape (N,) in int64 representing opaque vector IDs.
        lod: Level-of-Detail decimation metadata.
        partition_id: Optional array of shape (N,) in int32 IVF partition
            indices.
        nk: Optional array of shape (N,) in int32 in-degree counts.
        dist_centroid: Optional array of shape (N,) in float32 holding each
            point's distance to the projected corpus centroid.
    """

    positions: NDArray[np.float32]
    classes: NDArray[np.uint8]
    ids: NDArray[np.int64]
    lod: LodMetadata
    partition_id: NDArray[np.int32] | None = None
    nk: NDArray[np.int32] | None = None
    dist_centroid: NDArray[np.float32] | None = None

    def __post_init__(self) -> None:
        """Validate array dimensions and consistency."""
        n = self.positions.shape[0]
        if self.positions.ndim != 2 or self.positions.shape[1] != 3:
            msg = f"positions must be of shape (N, 3), got {self.positions.shape}"
            raise ValueError(msg)

        if len(self.classes) != n:
            msg = f"Length mismatch: positions ({n}) vs classes ({len(self.classes)})"
            raise ValueError(msg)

        if len(self.ids) != n:
            msg = f"Length mismatch: positions ({n}) vs ids ({len(self.ids)})"
            raise ValueError(msg)

        if self.partition_id is not None and len(self.partition_id) != n:
            msg = (
                f"Length mismatch: positions has {n} points but partition_id has "
                f"{len(self.partition_id)}"
            )
            raise ValueError(msg)

        if self.nk is not None and len(self.nk) != n:
            msg = f"Length mismatch: positions has {n} points but nk has {len(self.nk)}"
            raise ValueError(msg)

        if self.dist_centroid is not None and len(self.dist_centroid) != n:
            msg = (
                f"Length mismatch: positions has {n} points but dist_centroid has "
                f"{len(self.dist_centroid)}"
            )
            raise ValueError(msg)
