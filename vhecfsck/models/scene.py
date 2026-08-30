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


@dataclass(frozen=True)
class LodMetadata:
    """Level-of-detail sampling metadata for scene payloads.

    Attributes:
        requested_budget: Target point count requested by client.
        actual_count: Number of points included in the payload.
        decimation_method: Description of sampling method applied.
        complete: True if dataset is fully represented without decimation.
        has_tombstones: True if adapter provided tombstoned vectors.
    """

    requested_budget: int
    actual_count: int
    decimation_method: str
    complete: bool
    has_tombstones: bool


@dataclass(frozen=True)
class ScenePayload:
    """Structured 3D scene payload passed to front-end renderer.

    Attributes:
        positions: Array of shape (N, 3) in float32 display cube [-1, 1]^3.
        classes: Array of shape (N,) in uint8 representing PointClass values.
        ids: Array of shape (N,) in int64 representing opaque vector IDs.
        lod: Level-of-Detail decimation metadata.
        partition_id: Optional array of shape (N,) in int32 IVF partition indices.
        nk: Optional array of shape (N,) in int32 in-degree counts.
    """

    positions: NDArray[np.float32]
    classes: NDArray[np.uint8]
    ids: NDArray[np.int64]
    lod: LodMetadata
    partition_id: NDArray[np.int32] | None = None
    nk: NDArray[np.int32] | None = None

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
