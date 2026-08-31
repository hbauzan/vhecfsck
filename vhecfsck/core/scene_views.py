"""Colour-by attribute buffers and distribution charts for the visualizer.

P6-04. Every number the charts panel draws is produced here, in ``core/``, and
shipped to the browser already computed — the front end selects and renders, it
never derives. The in-degree histogram deliberately reuses the report's own
bucketing so the panel and the published report cannot disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.core.hubness import bucketed_histogram
from vhecfsck.models.scene import ColourBy, ScenePayload

#: Reason strings surfaced verbatim in the UI when a mode cannot be offered.
PARTITION_UNAVAILABLE = (
    "partition data is UNAVAILABLE for this target: the adapter does not expose "
    "IVF partition assignments"
)
NK_UNAVAILABLE = (
    "in-degree data is UNAVAILABLE for this scene: hubness did not run or the "
    "adapter could not supply neighbours"
)
EMPTY_SCENE = "scene contains no points"


@dataclass(frozen=True)
class ColourAttribute:
    """Per-point buffer driving colour for one colour-by mode.

    Attributes:
        mode: The mode this buffer was built for.
        values: Per-point scalar. Category index for categorical modes,
            normalised to ``[0, 1]`` for continuous ones.
        domain: ``(low, high)`` of the raw values before normalisation.
        categorical: True when ``values`` index a discrete palette rather than
            a continuous ramp.
        available: False when the mode cannot be offered for this scene.
        unavailable_reason: Why the mode is disabled, or None.
    """

    mode: ColourBy
    values: NDArray[np.float32]
    domain: tuple[float, float]
    categorical: bool
    available: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class DistributionCharts:
    """Bucketed distributions for the charts panel.

    Attributes:
        nk_histogram: In-degree buckets, identical to the report's.
        nk_log_y: True when the y axis should be logarithmic; the in-degree
            distribution is expected to be heavily skewed.
        partition_histogram: Partition-size buckets, or None when unavailable.
        partition_mean: Mean partition size, marked on the chart, or None.
        partition_unavailable_reason: Why partition data is missing, or None.
    """

    nk_histogram: tuple[dict[str, int], ...]
    nk_log_y: bool
    partition_histogram: tuple[dict[str, int], ...] | None
    partition_mean: float | None
    partition_unavailable_reason: str | None


def distances_to_centroid(
    positions: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Euclidean distance from each projected point to the corpus centroid.

    Args:
        positions: Array of shape ``(N, 3)`` in the display cube.

    Returns:
        Array of shape ``(N,)`` in float32. Empty input yields an empty array.
    """
    if positions.shape[0] == 0:
        return np.empty(0, dtype=np.float32)

    centroid = positions.mean(axis=0, dtype=np.float64)
    delta = positions.astype(np.float64) - centroid
    squared = np.einsum("ij,ij->i", delta, delta)
    np.clip(squared, 0.0, None, out=squared)
    distances: NDArray[np.float32] = np.asarray(np.sqrt(squared), dtype=np.float32)
    return distances


def _normalise(raw: NDArray[np.float64]) -> tuple[NDArray[np.float32], float, float]:
    lo = float(raw.min())
    hi = float(raw.max())
    if hi <= lo:
        return np.zeros(raw.shape[0], dtype=np.float32), lo, hi
    scaled = (raw - lo) / (hi - lo)
    return scaled.astype(np.float32), lo, hi


def _unavailable(mode: ColourBy, reason: str) -> ColourAttribute:
    return ColourAttribute(
        mode=mode,
        values=np.empty(0, dtype=np.float32),
        domain=(0.0, 0.0),
        categorical=False,
        available=False,
        unavailable_reason=reason,
    )


def colour_attribute(scene: ScenePayload, mode: ColourBy) -> ColourAttribute:
    """Build the attribute buffer for one colour-by mode.

    Args:
        scene: Scene to read positions and optional attributes from.
        mode: Mode to build.

    Returns:
        A :class:`ColourAttribute`. When the scene lacks the data a mode needs,
        ``available`` is False and ``unavailable_reason`` explains why — the
        mode is disabled with a reason rather than silently coloured wrong.
    """
    n = int(scene.positions.shape[0])
    if n == 0:
        return _unavailable(mode, EMPTY_SCENE)

    if mode is ColourBy.CLASS:
        return ColourAttribute(
            mode=mode,
            values=scene.classes.astype(np.float32),
            domain=(float(scene.classes.min()), float(scene.classes.max())),
            categorical=True,
            available=True,
            unavailable_reason=None,
        )

    if mode is ColourBy.PARTITION:
        if scene.partition_id is None:
            return _unavailable(mode, PARTITION_UNAVAILABLE)
        part = scene.partition_id
        return ColourAttribute(
            mode=mode,
            values=part.astype(np.float32),
            domain=(float(part.min()), float(part.max())),
            categorical=True,
            available=True,
            unavailable_reason=None,
        )

    if mode is ColourBy.NK:
        if scene.nk is None:
            return _unavailable(mode, NK_UNAVAILABLE)
        values, lo, hi = _normalise(scene.nk.astype(np.float64))
        return ColourAttribute(
            mode=mode,
            values=values,
            domain=(lo, hi),
            categorical=False,
            available=True,
            unavailable_reason=None,
        )

    raw = (
        scene.dist_centroid
        if scene.dist_centroid is not None
        else distances_to_centroid(scene.positions)
    )
    values, lo, hi = _normalise(raw.astype(np.float64))
    return ColourAttribute(
        mode=ColourBy.DISTANCE_TO_CENTROID,
        values=values,
        domain=(lo, hi),
        categorical=False,
        available=True,
        unavailable_reason=None,
    )


def partition_size_histogram(
    sizes: Sequence[int] | NDArray[np.integer],
    *,
    max_buckets: int = 64,
) -> tuple[tuple[dict[str, int], ...], float]:
    """Bucket true partition sizes and return them with their mean.

    Sizes must come from the adapter's partition statistics, never from a
    decimated scene: decimation changes the sizes, and a chart of decimated
    sizes would argue for a balance the index does not have.

    Args:
        sizes: One entry per partition, in vectors.
        max_buckets: Upper bound on bucket count.

    Returns:
        ``(buckets, mean_size)``. Mean is 0.0 for an empty input.
    """
    arr = np.asarray(sizes, dtype=np.int64).reshape(-1)
    if arr.size == 0:
        return ((), 0.0)
    buckets = bucketed_histogram(arr, max_buckets=max_buckets)
    return (tuple(buckets), float(arr.mean()))


def build_distribution_charts(
    n_k: Sequence[int] | NDArray[np.integer] | None,
    partition_sizes: Sequence[int] | NDArray[np.integer] | None,
    *,
    max_buckets: int = 64,
) -> DistributionCharts:
    """Assemble both charts for the distribution panel.

    Args:
        n_k: In-degree sample from the hubness metric, or None.
        partition_sizes: True partition sizes, or None when unavailable.
        max_buckets: Upper bound on bucket count for both charts.

    Returns:
        A :class:`DistributionCharts` ready to serialise to the client.
    """
    nk_arr = (
        np.asarray(n_k, dtype=np.int64).reshape(-1)
        if n_k is not None
        else np.empty(0, dtype=np.int64)
    )
    nk_buckets = tuple(bucketed_histogram(nk_arr, max_buckets=max_buckets))

    if partition_sizes is None:
        return DistributionCharts(
            nk_histogram=nk_buckets,
            nk_log_y=True,
            partition_histogram=None,
            partition_mean=None,
            partition_unavailable_reason=PARTITION_UNAVAILABLE,
        )

    part_buckets, mean = partition_size_histogram(
        partition_sizes, max_buckets=max_buckets
    )
    return DistributionCharts(
        nk_histogram=nk_buckets,
        nk_log_y=True,
        partition_histogram=part_buckets,
        partition_mean=mean,
        partition_unavailable_reason=None,
    )
