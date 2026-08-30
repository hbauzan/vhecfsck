"""Unit tests for level-of-detail decimation (P4-03)."""

from __future__ import annotations

import numpy as np
from vhecfsck.core.lod import decimate
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload


def _make_dummy_scene(
    n_healthy: int,
    n_hubs: int,
    n_antihubs: int,
    n_tombstones: int = 0,
    seed: int = 42,
) -> ScenePayload:
    n_total = n_healthy + n_hubs + n_antihubs + n_tombstones
    rng = np.random.default_rng(seed)

    positions = rng.uniform(-1.0, 1.0, size=(n_total, 3)).astype(np.float32)
    classes_list: list[int] = (
        [PointClass.HUB.value] * n_hubs
        + [PointClass.ANTIHUB.value] * n_antihubs
        + [PointClass.TOMBSTONE.value] * n_tombstones
        + [PointClass.HEALTHY.value] * n_healthy
    )
    classes = np.array(classes_list, dtype=np.uint8)
    ids = np.arange(n_total, dtype=np.int64)

    lod = LodMetadata(
        requested_budget=n_total,
        actual_count=n_total,
        decimation_method="none",
        complete=True,
        has_tombstones=n_tombstones > 0,
    )

    return ScenePayload(
        positions=positions,
        classes=classes,
        ids=ids,
        lod=lod,
    )


def test_decimate_scene_already_under_budget() -> None:
    """Scene <= budget passes through unchanged with complete=True."""
    scene = _make_dummy_scene(n_healthy=50, n_hubs=5, n_antihubs=5)

    decimated = decimate(scene, budget=100)

    assert decimated.lod.complete is True
    assert decimated.lod.actual_count == 60
    assert len(decimated.positions) == 60
    assert np.array_equal(decimated.ids, scene.ids)


def test_decimate_preserves_all_hubs_and_antihubs() -> None:
    """Class-stratified decimation retains 100% of hubs and antihubs."""
    scene = _make_dummy_scene(n_healthy=1000, n_hubs=10, n_antihubs=5, seed=123)

    # Decimate to budget 50 (hubs=10, antihubs=5, remaining healthy=35)
    decimated = decimate(scene, budget=50, seed=42)

    assert len(decimated.positions) == 50
    assert decimated.lod.complete is False
    assert decimated.lod.actual_count == 50

    hubs_count = int(np.sum(decimated.classes == PointClass.HUB.value))
    antihubs_count = int(np.sum(decimated.classes == PointClass.ANTIHUB.value))

    assert hubs_count == 10
    assert antihubs_count == 5


def test_decimate_output_size_strictly_bounded() -> None:
    """Output count never exceeds requested budget."""
    scene = _make_dummy_scene(n_healthy=500, n_hubs=20, n_antihubs=10)

    for budget in [15, 30, 100, 300]:
        decimated = decimate(scene, budget=budget, seed=7)
        assert len(decimated.positions) <= budget
        assert decimated.lod.actual_count <= budget


def test_decimate_determinism_under_seed() -> None:
    """Fixed seed produces bit-identical decimation results."""
    scene = _make_dummy_scene(n_healthy=300, n_hubs=8, n_antihubs=4)

    dec1 = decimate(scene, budget=50, seed=99)
    dec2 = decimate(scene, budget=50, seed=99)

    assert np.array_equal(dec1.ids, dec2.ids)
    assert np.array_equal(dec1.positions, dec2.positions)
    assert dec1.lod == dec2.lod
