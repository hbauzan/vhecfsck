"""Level-of-Detail decimation module for 3D visualizer scenes."""

from __future__ import annotations

import numpy as np

from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload


def decimate(
    scene: ScenePayload,
    budget: int,
    *,
    seed: int | None = None,
) -> ScenePayload:
    """Apply class-stratified and spatially-aware decimation to a ScenePayload.

    Priority classes (HUB, ANTIHUB, QUERY, etc.) are preserved up to budget.
    Healthy points are spatially thinned via voxel grid before random filling.

    Args:
        scene: Input ScenePayload to decimate.
        budget: Maximum target point count.
        seed: Optional RNG seed for deterministic sampling.

    Returns:
        Decimated ScenePayload instance.
    """
    total_points = len(scene.positions)
    if total_points <= budget:
        # Already under budget; return scene unchanged with updated requested_budget
        new_lod = LodMetadata(
            requested_budget=budget,
            actual_count=total_points,
            decimation_method="none",
            complete=True,
            has_tombstones=scene.lod.has_tombstones,
        )
        return ScenePayload(
            positions=scene.positions,
            classes=scene.classes,
            ids=scene.ids,
            lod=new_lod,
            partition_id=scene.partition_id,
            nk=scene.nk,
        )

    rng = np.random.default_rng(seed)

    # Class priority groups
    priority_mask = (
        (scene.classes == PointClass.HUB.value)
        | (scene.classes == PointClass.ANTIHUB.value)
        | (scene.classes == PointClass.QUERY.value)
        | (scene.classes == PointClass.TRUE_NEIGHBOUR.value)
        | (scene.classes == PointClass.RETURNED.value)
        | (scene.classes == PointClass.MISSED.value)
    )

    priority_indices = np.where(priority_mask)[0]
    ordinary_indices = np.where(~priority_mask)[0]

    selected_indices: list[int] = []

    # 1. Retain priority points up to budget
    if len(priority_indices) > 0:
        if len(priority_indices) <= budget:
            selected_indices.extend(priority_indices.tolist())
        else:
            # Budget insufficient for all priority points; random sample priority points
            perm = rng.permutation(len(priority_indices))
            selected_indices.extend(priority_indices[perm[:budget]].tolist())

    remaining_budget = budget - len(selected_indices)

    # 2. Voxel-grid thinning for ordinary/healthy points if budget remains
    if remaining_budget > 0 and len(ordinary_indices) > 0:
        if len(ordinary_indices) <= remaining_budget:
            selected_indices.extend(ordinary_indices.tolist())
        else:
            ord_positions = scene.positions[ordinary_indices]
            # Map [-1, 1] to voxel grid index [0, grid_size - 1]
            grid_size = 16
            voxel_coords = np.floor((ord_positions + 1.0) * 0.5 * grid_size).astype(
                np.int32
            )
            voxel_coords = np.clip(voxel_coords, 0, grid_size - 1)

            # Assign unique 1D key per 3D voxel
            voxel_keys = (
                voxel_coords[:, 0] * grid_size * grid_size
                + voxel_coords[:, 1] * grid_size
                + voxel_coords[:, 2]
            )

            # Pick first point in each occupied voxel
            _, unique_idx = np.unique(voxel_keys, return_index=True)
            voxel_selected = ordinary_indices[unique_idx]

            if len(voxel_selected) <= remaining_budget:
                selected_indices.extend(voxel_selected.tolist())
                unselected_mask = np.isin(ordinary_indices, voxel_selected, invert=True)
                unselected_ordinary = ordinary_indices[unselected_mask]
                still_needed = remaining_budget - len(voxel_selected)

                if still_needed > 0 and len(unselected_ordinary) > 0:
                    perm = rng.permutation(len(unselected_ordinary))
                    selected_indices.extend(
                        unselected_ordinary[perm[:still_needed]].tolist()
                    )
            else:
                # Voxel count exceeds remaining budget; sample from voxel centers
                perm = rng.permutation(len(voxel_selected))
                selected_indices.extend(
                    voxel_selected[perm[:remaining_budget]].tolist()
                )

    sel_arr = np.array(selected_indices, dtype=np.int64)
    # Sort selected indices to maintain index order
    sel_arr = np.sort(sel_arr)

    new_lod = LodMetadata(
        requested_budget=budget,
        actual_count=len(sel_arr),
        decimation_method="class-stratified+voxel-grid",
        complete=False,
        has_tombstones=scene.lod.has_tombstones,
    )

    part_id = scene.partition_id[sel_arr] if scene.partition_id is not None else None
    nk_arr = scene.nk[sel_arr] if scene.nk is not None else None

    return ScenePayload(
        positions=scene.positions[sel_arr],
        classes=scene.classes[sel_arr],
        ids=scene.ids[sel_arr],
        lod=new_lod,
        partition_id=part_id,
        nk=nk_arr,
    )
