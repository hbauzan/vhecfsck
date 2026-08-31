"""Assembles scene payloads from an adapter for the visualizer endpoints.

Framework-free, so the assembly — including the guard that refuses to invent
tombstone positions — is covered by the default suite rather than by whichever
tests happen to run with the ``server`` extra installed.

No metric is computed here. Everything numeric comes from ``core``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from vhecfsck.core.camera import build_tour, derive_presets, sample_tour
from vhecfsck.core.lod import (
    ChunkPlan,
    decimate_chunk,
    plan_chunks,
    resolve_display_budget,
)
from vhecfsck.core.projection import project_to_3d
from vhecfsck.core.scene_views import distances_to_centroid
from vhecfsck.core.tombstones import (
    TombstoneLayer,
    assert_no_fabricated_tombstones,
    resolve_tombstone_layer,
)
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload

#: Vectors pulled per adapter batch while assembling a scene.
READ_BATCH = 50_000

#: Projection is fitted on a sample rather than the whole corpus; a million
#: rows do not move the principal axes further than this many already have.
PROJECTION_SAMPLE = 50_000


@dataclass(frozen=True)
class SceneBundle:
    """A scene plus everything the client needs alongside it.

    Attributes:
        scene: The chunk to send.
        plan: Chunk plan the scene was cut from.
        tombstones: What the tombstone layer may display.
        budget_reason: Why the granted budget differs from the request, if it
            does.
        partition_sizes: True partition sizes for the charts panel, or None.
    """

    scene: ScenePayload
    plan: ChunkPlan
    tombstones: TombstoneLayer
    budget_reason: str | None
    partition_sizes: np.ndarray | None


@dataclass(frozen=True)
class AssembledScene:
    """A projected corpus ready to be sliced into progressive chunks.

    Caching one of these across ``GET /api/scene?chunk=i`` is what makes a
    million-point stream cheap: projection runs once, each chunk is a slice.
    """

    full: ScenePayload
    tombstones: TombstoneLayer
    budget_reason: str | None
    partition_sizes: np.ndarray | None
    granted: int
    seed: int

    def plan(self) -> ChunkPlan:
        """Chunk plan for the granted budget."""
        n = int(self.full.positions.shape[0])
        return plan_chunks(total_available=n, budget=max(1, self.granted))

    def chunk(self, chunk_index: int) -> ScenePayload:
        """Materialise one progressive chunk."""
        if int(self.full.positions.shape[0]) == 0:
            return self.full
        return decimate_chunk(
            self.full, plan=self.plan(), chunk_index=chunk_index, seed=self.seed
        )

    def bundle(self, chunk_index: int = 0) -> SceneBundle:
        """Wrap ``chunk_index`` as the object the route returns."""
        return SceneBundle(
            scene=self.chunk(chunk_index),
            plan=self.plan(),
            tombstones=self.tombstones,
            budget_reason=self.budget_reason,
            partition_sizes=self.partition_sizes,
        )


def _classify(
    ids: np.ndarray,
    hub_ids: frozenset[int],
    antihub_ids: frozenset[int],
) -> np.ndarray:
    classes = np.full(ids.shape[0], PointClass.HEALTHY.value, dtype=np.uint8)
    if hub_ids:
        classes[np.isin(ids, np.array(sorted(hub_ids), dtype=np.int64))] = (
            PointClass.HUB.value
        )
    if antihub_ids:
        classes[np.isin(ids, np.array(sorted(antihub_ids), dtype=np.int64))] = (
            PointClass.ANTIHUB.value
        )
    return classes


def _read_corpus(adapter: Any, limit: int) -> tuple[np.ndarray, np.ndarray]:
    id_blocks: list[np.ndarray] = []
    vector_blocks: list[np.ndarray] = []
    collected = 0
    for batch in adapter.iter_live_vectors(batch_size=READ_BATCH):
        id_blocks.append(batch.ids)
        vector_blocks.append(batch.vectors)
        collected += int(batch.ids.shape[0])
        if collected >= limit:
            break

    if not id_blocks:
        return np.empty(0, dtype=np.int64), np.zeros((0, 0), dtype=np.float32)

    ids = np.concatenate(id_blocks)[:limit]
    vectors = np.concatenate(vector_blocks, axis=0)[:limit]
    return ids, np.ascontiguousarray(vectors, dtype=np.float32)


def _partition_buffer(adapter: Any, ids: np.ndarray) -> np.ndarray | None:
    """Per-point partition ids, or None when the engine cannot supply them.

    The adapter protocol exposes partition *sizes*, not per-vector assignments,
    so this is None for every adapter that does not opt in with an extra
    ``partition_assignments`` method. Colour-by-partition then reports itself
    UNAVAILABLE rather than colouring points by a number nobody read.
    """
    assignments = getattr(adapter, "partition_assignments", None)
    if not callable(assignments):
        return None
    try:
        mapping = assignments(ids)
    except (AttributeError, NotImplementedError, TypeError):
        return None
    if mapping is None:
        return None
    return np.asarray(mapping, dtype=np.int32)


def findings_from_report(
    report: Mapping[str, Any] | None,
) -> tuple[frozenset[int], frozenset[int], tuple[int, ...] | None]:
    """Extract hub ids, anti-hub ids and the in-degree sample from a report.

    Args:
        report: JSON-shaped audit report, or None when none is loaded.

    Returns:
        ``(hub_ids, antihub_ids, n_k)``. ``n_k`` is None when hubness did not
        publish an in-degree sample.
    """
    if not report:
        return frozenset(), frozenset(), None

    hubs: list[int] = []
    antis: list[int] = []
    n_k: tuple[int, ...] | None = None
    metrics = report.get("metrics") or []
    if isinstance(metrics, Mapping):
        metrics = list(metrics.values())
    for metric in metrics:
        if not isinstance(metric, Mapping):
            continue
        detail = metric.get("detail") or {}
        if not isinstance(detail, Mapping):
            continue
        if "hub_ids" in detail:
            hubs.extend(int(x) for x in detail["hub_ids"])
        if "antihub_ids" in detail:
            antis.extend(int(x) for x in detail["antihub_ids"])
        if n_k is None and "n_k" in detail:
            n_k = tuple(int(x) for x in detail["n_k"])
    return frozenset(hubs), frozenset(antis), n_k


def _partition_sizes(adapter: Any) -> np.ndarray | None:
    """True partition sizes for the charts panel, or None when unavailable."""
    try:
        stats = adapter.partitions()
    except (AttributeError, NotImplementedError):
        return None
    if stats is None:
        return None
    return np.asarray(stats.sizes, dtype=np.int64)


def assemble_scene(
    adapter: Any,
    *,
    requested_budget: int,
    device_max_points: int,
    seed: int = 1337,
    hub_ids: frozenset[int] = frozenset(),
    antihub_ids: frozenset[int] = frozenset(),
) -> AssembledScene:
    """Read an adapter and project the corpus once.

    Args:
        adapter: An open, read-only index adapter.
        requested_budget: Display budget the client asked for.
        device_max_points: Points the client says it can sustain.
        seed: Shared across chunks of one stream so they stay disjoint.
        hub_ids: Ids the audit flagged as hubs, when a report is loaded.
        antihub_ids: Ids the audit flagged as anti-hubs.

    Returns:
        An :class:`AssembledScene` from which any chunk can be sliced.

    Raises:
        ValueError: If the scene would carry fabricated tombstone positions.
    """
    decision = resolve_display_budget(
        requested_budget, device_max_points=device_max_points
    )
    counts = adapter.counts()
    capabilities = adapter.capabilities
    partition_sizes = _partition_sizes(adapter)

    ids, vectors = _read_corpus(adapter, decision.granted)
    n_points = int(ids.shape[0])

    tombstones = resolve_tombstone_layer(
        report_deleted_counts=bool(
            getattr(capabilities, "report_deleted_counts", False)
        ),
        deleted=getattr(counts, "deleted", None),
        positions_available=False,
    )

    if n_points == 0:
        empty = ScenePayload(
            positions=np.empty((0, 3), dtype=np.float32),
            classes=np.empty(0, dtype=np.uint8),
            ids=np.empty(0, dtype=np.int64),
            lod=LodMetadata(
                requested_budget=decision.granted,
                actual_count=0,
                decimation_method="none",
                complete=True,
                has_tombstones=False,
                total_available=0,
                tombstone_count=tombstones.count,
                tombstone_reason=tombstones.reason,
            ),
        )
        return AssembledScene(
            full=empty,
            tombstones=tombstones,
            budget_reason=decision.reason,
            partition_sizes=partition_sizes,
            granted=decision.granted,
            seed=seed,
        )

    projection = project_to_3d(
        [vectors], n_components=3, seed=seed, sample_size=PROJECTION_SAMPLE
    )
    classes = _classify(ids, hub_ids, antihub_ids)

    full = ScenePayload(
        positions=projection.positions,
        classes=classes,
        ids=ids,
        lod=LodMetadata(
            requested_budget=decision.granted,
            actual_count=n_points,
            decimation_method="none",
            complete=True,
            has_tombstones=tombstones.renderable,
            total_available=n_points,
            tombstone_count=tombstones.count,
            tombstone_reason=tombstones.reason,
        ),
        partition_id=_partition_buffer(adapter, ids),
        dist_centroid=distances_to_centroid(projection.positions),
    )

    # Refuse to ship invented deleted-vector positions, whatever produced them.
    assert_no_fabricated_tombstones(full.classes, tombstones)

    return AssembledScene(
        full=full,
        tombstones=tombstones,
        budget_reason=decision.reason,
        partition_sizes=partition_sizes,
        granted=decision.granted,
        seed=seed,
    )


def build_scene_bundle(
    adapter: Any,
    *,
    requested_budget: int,
    device_max_points: int,
    chunk_index: int = 0,
    seed: int = 1337,
    hub_ids: frozenset[int] = frozenset(),
    antihub_ids: frozenset[int] = frozenset(),
) -> SceneBundle:
    """Read an adapter and cut one progressive chunk out of the result.

    Args:
        adapter: An open, read-only index adapter.
        requested_budget: Display budget the client asked for.
        device_max_points: Points the client says it can sustain.
        chunk_index: Which chunk of the progressive stream to return.
        seed: Shared across chunks of one stream so they stay disjoint.
        hub_ids: Ids the audit flagged as hubs, when a report is loaded.
        antihub_ids: Ids the audit flagged as anti-hubs.

    Returns:
        A :class:`SceneBundle`.

    Raises:
        ValueError: If the scene would carry fabricated tombstone positions.
    """
    return assemble_scene(
        adapter,
        requested_budget=requested_budget,
        device_max_points=device_max_points,
        seed=seed,
        hub_ids=hub_ids,
        antihub_ids=antihub_ids,
    ).bundle(chunk_index)


def presets_payload(scene: ScenePayload) -> dict[str, Any]:
    """Serialise camera presets and the guided tour for the client.

    Args:
        scene: Scene the presets should aim at.

    Returns:
        A JSON-safe dict of presets, tour steps and the sampled frame count.
        ``tour`` is None when no preset is available to script.
    """
    presets = derive_presets(scene)
    payload: dict[str, Any] = {
        "presets": {
            name: {
                "name": preset.name,
                "position": list(preset.position),
                "target": list(preset.target),
                "up": list(preset.up),
                "fov_degrees": preset.fov_degrees,
                "caption": preset.caption,
                "available": preset.available,
                "unavailable_reason": preset.unavailable_reason,
            }
            for name, preset in presets.items()
        },
        "tour": None,
    }

    try:
        timeline = build_tour(presets)
    except ValueError:
        return payload

    payload["tour"] = {
        "fps": timeline.fps,
        "duration_seconds": timeline.duration_seconds,
        "total_frames": timeline.total_frames,
        "steps": [
            {
                "preset": step.preset,
                "caption": step.caption,
                "transition_seconds": step.transition_seconds,
                "hold_seconds": step.hold_seconds,
            }
            for step in timeline.steps
        ],
    }
    payload["frame_count"] = len(sample_tour(timeline, presets))
    return payload
