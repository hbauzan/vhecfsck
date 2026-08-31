"""Level-of-detail decimation and progressive chunking for visualizer scenes.

P4-03 introduced class-stratified decimation. P6-01 adds a deterministic
*selection order* on top of it, so a large corpus can be streamed as a coarse
first chunk followed by refinement chunks without ever repeating a point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload

#: Points in the first chunk. Sized so the findings paint before the background.
COARSE_CHUNK_POINTS = 50_000

#: Points added per refinement chunk after the coarse pass.
REFINEMENT_CHUNK_POINTS = 100_000

#: Budget the server offers when the client states no preference. Chosen to sit
#: inside the measured integrated-graphics envelope recorded in
#: ``docs/perf/visualizer.md``; do not raise it without a new measurement.
DEFAULT_DISPLAY_BUDGET = 200_000

#: Ceiling no client may exceed regardless of what it claims it can render.
HARD_MAX_DISPLAY_BUDGET = 1_000_000

_PRIORITY_CLASSES = (
    PointClass.HUB,
    PointClass.ANTIHUB,
    PointClass.QUERY,
    PointClass.TRUE_NEIGHBOUR,
    PointClass.RETURNED,
    PointClass.MISSED,
)

_VOXEL_MIN = 8
_VOXEL_MAX = 256
#: Voxels per retained point. >1 leaves headroom so occupancy stays sparse and
#: the grid actually thins space instead of collapsing to one point per cell.
_VOXEL_OVERSAMPLE = 8.0

DECIMATION_METHOD = "class-stratified+voxel-grid"


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of validating a requested display budget.

    Attributes:
        requested: Budget the caller asked for.
        granted: Budget that may actually be rendered.
        accepted: True when ``granted == requested``.
        reason: Human-readable refusal reason, or None when accepted.
    """

    requested: int
    granted: int
    accepted: bool
    reason: str | None


@dataclass(frozen=True)
class ChunkPlan:
    """Deterministic split of a display budget into progressive chunks.

    Attributes:
        chunk_sizes: Point count per chunk, in stream order.
        budget: Total points the plan will deliver.
        total_available: Live points available before decimation.
    """

    chunk_sizes: tuple[int, ...]
    budget: int
    total_available: int

    @property
    def chunk_count(self) -> int:
        """Number of chunks in the stream."""
        return len(self.chunk_sizes)

    def offset(self, chunk_index: int) -> int:
        """Index of the first point of ``chunk_index`` within the selection."""
        return sum(self.chunk_sizes[:chunk_index])


def resolve_display_budget(
    requested: int,
    *,
    device_max_points: int,
    hard_max: int = HARD_MAX_DISPLAY_BUDGET,
) -> BudgetDecision:
    """Validate a requested budget against the device and the hard ceiling.

    A budget the device cannot support is refused with a reason rather than
    attempted; attempting it is what hangs the browser tab.

    Args:
        requested: Budget the client asked for.
        device_max_points: Points this client reports it can sustain.
        hard_max: Absolute ceiling regardless of the client's claim.

    Returns:
        A :class:`BudgetDecision`. ``granted`` is always renderable.

    Raises:
        ValueError: If ``requested`` is below one.
    """
    if requested < 1:
        msg = "budget must be >= 1"
        raise ValueError(msg)

    ceiling = min(int(device_max_points), int(hard_max))
    if requested <= ceiling:
        return BudgetDecision(
            requested=requested, granted=requested, accepted=True, reason=None
        )

    limit_name = "device capability" if device_max_points < hard_max else "hard ceiling"
    reason = (
        f"requested budget {requested} exceeds the {limit_name} of {ceiling} points; "
        f"render at most {ceiling}"
    )
    return BudgetDecision(
        requested=requested, granted=ceiling, accepted=False, reason=reason
    )


def plan_chunks(
    total_available: int,
    budget: int,
    *,
    coarse_points: int = COARSE_CHUNK_POINTS,
    refinement_points: int = REFINEMENT_CHUNK_POINTS,
) -> ChunkPlan:
    """Split a budget into a coarse chunk followed by refinement chunks.

    Args:
        total_available: Live points available before decimation.
        budget: Points to deliver in total across all chunks.
        coarse_points: Size of the first chunk.
        refinement_points: Size of each subsequent chunk.

    Returns:
        A :class:`ChunkPlan` whose sizes sum to ``min(budget, total_available)``.

    Raises:
        ValueError: If ``budget`` or the chunk sizes are below one.
    """
    if budget < 1:
        msg = "budget must be >= 1"
        raise ValueError(msg)
    if coarse_points < 1 or refinement_points < 1:
        msg = "chunk sizes must be >= 1"
        raise ValueError(msg)

    deliverable = min(int(budget), max(0, int(total_available)))
    if deliverable <= coarse_points:
        sizes = (deliverable,) if deliverable > 0 else (0,)
        return ChunkPlan(
            chunk_sizes=sizes,
            budget=deliverable,
            total_available=int(total_available),
        )

    sizes_list = [coarse_points]
    remaining = deliverable - coarse_points
    while remaining > 0:
        take = min(refinement_points, remaining)
        sizes_list.append(take)
        remaining -= take

    return ChunkPlan(
        chunk_sizes=tuple(sizes_list),
        budget=deliverable,
        total_available=int(total_available),
    )


def _voxel_representatives(
    positions: NDArray[np.float32],
    candidates: NDArray[np.int64],
    target: int,
) -> NDArray[np.int64]:
    """Pick one point per occupied voxel, grid sized to the target count."""
    grid_size = round((max(1, target) * _VOXEL_OVERSAMPLE) ** (1.0 / 3.0))
    grid_size = max(_VOXEL_MIN, min(_VOXEL_MAX, grid_size))

    coords = np.floor((positions[candidates] + 1.0) * 0.5 * grid_size).astype(np.int32)
    np.clip(coords, 0, grid_size - 1, out=coords)
    keys = (
        coords[:, 0].astype(np.int64) * grid_size * grid_size
        + coords[:, 1].astype(np.int64) * grid_size
        + coords[:, 2].astype(np.int64)
    )
    _, first_in_voxel = np.unique(keys, return_index=True)
    return candidates[first_in_voxel]


def selection_order(
    scene: ScenePayload,
    budget: int,
    *,
    seed: int | None = None,
) -> NDArray[np.int64]:
    """Rank point indices by streaming priority, truncated to ``budget``.

    The order is the contract the progressive loader relies on: every priority
    point (hub, anti-hub, probe class) precedes every ordinary point, and voxel
    representatives precede the random fill. Slicing this array yields chunks
    that are disjoint by construction.

    Args:
        scene: Scene to rank.
        budget: Maximum number of indices to return.
        seed: Seed for the sampling steps; None uses fresh entropy.

    Returns:
        Array of indices into ``scene.positions``, in stream order.
    """
    rng = np.random.default_rng(seed)
    total = int(scene.positions.shape[0])
    budget = max(0, min(int(budget), total))
    if budget == 0:
        return np.empty(0, dtype=np.int64)

    priority_mask = np.isin(
        scene.classes, np.array([c.value for c in _PRIORITY_CLASSES], dtype=np.uint8)
    )
    priority = np.flatnonzero(priority_mask).astype(np.int64)
    ordinary = np.flatnonzero(~priority_mask).astype(np.int64)

    if priority.size >= budget:
        chosen = priority[rng.permutation(priority.size)[:budget]]
        return np.sort(chosen)

    parts: list[NDArray[np.int64]] = [np.sort(priority)]
    remaining = budget - int(priority.size)

    if remaining > 0 and ordinary.size > 0:
        if ordinary.size <= remaining:
            parts.append(np.sort(ordinary))
        else:
            voxel = _voxel_representatives(scene.positions, ordinary, remaining)
            if voxel.size <= remaining:
                parts.append(np.sort(voxel))
                still_needed = remaining - int(voxel.size)
                if still_needed > 0:
                    leftover = ordinary[np.isin(ordinary, voxel, invert=True)]
                    if leftover.size > 0:
                        picked = leftover[rng.permutation(leftover.size)[:still_needed]]
                        parts.append(np.sort(picked))
            else:
                picked = voxel[rng.permutation(voxel.size)[:remaining]]
                parts.append(np.sort(picked))

    return np.concatenate(parts).astype(np.int64, copy=False)


def _take(
    scene: ScenePayload,
    indices: NDArray[np.int64],
    lod: LodMetadata,
) -> ScenePayload:
    return ScenePayload(
        positions=scene.positions[indices],
        classes=scene.classes[indices],
        ids=scene.ids[indices],
        lod=lod,
        partition_id=(
            scene.partition_id[indices] if scene.partition_id is not None else None
        ),
        nk=scene.nk[indices] if scene.nk is not None else None,
        dist_centroid=(
            scene.dist_centroid[indices] if scene.dist_centroid is not None else None
        ),
    )


def decimate(
    scene: ScenePayload,
    budget: int,
    *,
    seed: int | None = None,
) -> ScenePayload:
    """Apply class-stratified and spatially-aware decimation to a scene.

    Priority classes (hubs, anti-hubs, probe classes) are preserved up to the
    budget. Ordinary points are spatially thinned on a voxel grid before a
    random fill tops the selection up.

    Args:
        scene: Input scene to decimate.
        budget: Maximum target point count.
        seed: Optional RNG seed for deterministic sampling.

    Returns:
        A decimated scene, ids in ascending order.
    """
    total_points = int(scene.positions.shape[0])
    if total_points <= budget:
        return _take(
            scene,
            np.arange(total_points, dtype=np.int64),
            LodMetadata(
                requested_budget=budget,
                actual_count=total_points,
                decimation_method="none",
                complete=True,
                has_tombstones=scene.lod.has_tombstones,
                total_available=total_points,
                tombstone_count=scene.lod.tombstone_count,
                tombstone_reason=scene.lod.tombstone_reason,
            ),
        )

    chosen = np.sort(selection_order(scene, budget, seed=seed))
    return _take(
        scene,
        chosen,
        LodMetadata(
            requested_budget=budget,
            actual_count=int(chosen.size),
            decimation_method=DECIMATION_METHOD,
            complete=False,
            has_tombstones=scene.lod.has_tombstones,
            total_available=total_points,
            tombstone_count=scene.lod.tombstone_count,
            tombstone_reason=scene.lod.tombstone_reason,
        ),
    )


def decimate_chunk(
    scene: ScenePayload,
    *,
    plan: ChunkPlan,
    chunk_index: int,
    seed: int | None = None,
) -> ScenePayload:
    """Return one chunk of a progressively streamed scene.

    Args:
        scene: Full scene to draw from.
        plan: Chunk plan produced by :func:`plan_chunks`.
        chunk_index: Zero-based chunk to materialise.
        seed: Seed shared across every chunk of one stream; the same seed must
            be used for all chunks or they will overlap.

    Returns:
        The requested chunk, ids in ascending order within the chunk.

    Raises:
        ValueError: If ``chunk_index`` is outside the plan.
    """
    if chunk_index < 0 or chunk_index >= plan.chunk_count:
        msg = f"chunk_index {chunk_index} outside plan of {plan.chunk_count} chunks"
        raise ValueError(msg)

    order = selection_order(scene, plan.budget, seed=seed)
    start = plan.offset(chunk_index)
    stop = start + plan.chunk_sizes[chunk_index]
    indices = np.sort(order[start:stop])

    is_last = chunk_index == plan.chunk_count - 1
    method = "none" if plan.budget >= plan.total_available else DECIMATION_METHOD
    return _take(
        scene,
        indices,
        LodMetadata(
            requested_budget=plan.budget,
            actual_count=int(indices.size),
            decimation_method=method,
            complete=is_last,
            has_tombstones=scene.lod.has_tombstones,
            chunk_index=chunk_index,
            chunk_count=plan.chunk_count,
            total_available=plan.total_available,
            tombstone_count=scene.lod.tombstone_count,
            tombstone_reason=scene.lod.tombstone_reason,
        ),
    )
