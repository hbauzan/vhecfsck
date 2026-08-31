"""Tombstone layer resolution and the ghost-neighbourhood view.

P6-05. Most engines cannot hand back the coordinates of a deleted vector. When
that is the case the layer shows a count and an explanation — it never invents
positions. A fabricated tombstone cloud would be the most misleading thing this
UI could draw, because it would look exactly like evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import MetricSpace, VectorBatch

NO_DELETION_CAPABILITY = (
    "this adapter cannot report deleted counts, so the number of tombstones is "
    "UNAVAILABLE"
)
COUNT_ONLY = (
    "this engine reports how many vectors are deleted but cannot return their "
    "coordinates, so tombstones are shown as a count rather than as points"
)


@dataclass(frozen=True)
class TombstoneLayer:
    """What the tombstone layer may legitimately display.

    Attributes:
        renderable: True only when real tombstone positions were read.
        count: Deleted vectors reported by the adapter, or None.
        reason: Why positions are absent, or None when renderable.
    """

    renderable: bool
    count: int | None
    reason: str | None


@dataclass(frozen=True)
class GhostNeighbourhood:
    """Which of a query's nearest neighbours are dead.

    This is path blocking in visual form: the neighbours are still in the
    graph, still on the route the search walks, and no longer retrievable.

    Attributes:
        query_id: The probed query.
        dead_neighbours: Nearest neighbours that are tombstoned.
        live_neighbours: Nearest neighbours that are still retrievable.
        blocked_fraction: Share of the neighbourhood that is dead.
        available: False when the view could not be computed.
        unavailable_reason: Why it could not be computed, or None.
    """

    query_id: int
    dead_neighbours: tuple[int, ...]
    live_neighbours: tuple[int, ...]
    blocked_fraction: float
    available: bool
    unavailable_reason: str | None


def resolve_tombstone_layer(
    *,
    report_deleted_counts: bool,
    deleted: int | None,
    positions_available: bool = False,
) -> TombstoneLayer:
    """Decide what the tombstone layer is allowed to show.

    Args:
        report_deleted_counts: The adapter's ``report_deleted_counts``
            capability.
        deleted: Deleted vector count, when the adapter supplied one.
        positions_available: True only when tombstone coordinates were
            actually read from the engine.

    Returns:
        A :class:`TombstoneLayer`. ``renderable`` is True only when both the
        capability and real positions are present.
    """
    if not report_deleted_counts or deleted is None:
        return TombstoneLayer(
            renderable=False, count=None, reason=NO_DELETION_CAPABILITY
        )

    if not positions_available:
        return TombstoneLayer(renderable=False, count=int(deleted), reason=COUNT_ONLY)

    return TombstoneLayer(renderable=True, count=int(deleted), reason=None)


def assert_no_fabricated_tombstones(
    classes: NDArray[np.uint8],
    layer: TombstoneLayer,
    *,
    tombstone_class: int = 3,
) -> None:
    """Fail loudly if a scene carries tombstone points the layer may not draw.

    Args:
        classes: Per-point class array of the scene about to be sent.
        layer: The resolved tombstone layer.
        tombstone_class: Numeric value of ``PointClass.TOMBSTONE``.

    Raises:
        ValueError: If the scene contains tombstone points while the layer is
            not renderable — that combination can only mean invented positions.
    """
    if layer.renderable:
        return
    painted = int(np.count_nonzero(classes == tombstone_class))
    if painted:
        msg = (
            f"scene carries {painted} tombstone points but their positions were "
            f"never read ({layer.reason}); refusing to emit fabricated positions"
        )
        raise ValueError(msg)


def ghost_neighbourhood(
    *,
    query_id: int,
    corpus_batches: Iterable[VectorBatch],
    tombstoned_ids: frozenset[int],
    metric_space: MetricSpace,
    k: int,
    working_set_mb: float = 256.0,
) -> GhostNeighbourhood:
    """Split a query's true neighbourhood into live and tombstoned members.

    The corpus passed here must include the deleted vectors; that is the whole
    point of the view, and it is only possible on an engine that can read them.

    Args:
        query_id: Point to inspect. May itself be tombstoned.
        corpus_batches: Live *and* deleted vectors.
        tombstoned_ids: Ids that are deleted.
        metric_space: Distance space the index was built in.
        k: Neighbourhood size, excluding the query itself.
        working_set_mb: Blocking budget for the ground-truth pass.

    Returns:
        A :class:`GhostNeighbourhood`; unavailable rather than raising when the
        query is absent from the supplied corpus.

    Raises:
        ValueError: If ``k`` is below one.
    """
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)

    collected = list(corpus_batches)
    if not collected:
        return GhostNeighbourhood(
            query_id=int(query_id),
            dead_neighbours=(),
            live_neighbours=(),
            blocked_fraction=0.0,
            available=False,
            unavailable_reason="the supplied corpus is empty",
        )

    ids = np.concatenate([b.ids for b in collected]).astype(np.int64, copy=False)
    vectors = np.ascontiguousarray(
        np.concatenate([b.vectors for b in collected], axis=0), dtype=np.float32
    )
    matches = np.flatnonzero(ids == int(query_id))
    if matches.size == 0:
        return GhostNeighbourhood(
            query_id=int(query_id),
            dead_neighbours=(),
            live_neighbours=(),
            blocked_fraction=0.0,
            available=False,
            unavailable_reason=(
                f"vector {query_id} is absent from the supplied corpus, including "
                "its deleted rows"
            ),
        )

    row = int(matches[0])
    n_total = int(ids.shape[0])
    gt = exact_knn(
        [VectorBatch(ids=ids, vectors=vectors)],
        vectors[row : row + 1],
        min(k + 1, n_total),
        metric_space,
        working_set_mb=working_set_mb,
        n_total=n_total,
    )

    dead: list[int] = []
    live: list[int] = []
    for column in range(int(gt.ids.shape[1])):
        candidate = int(gt.ids[0, column])
        if candidate < 0 or candidate == int(query_id):
            continue
        if candidate in tombstoned_ids:
            dead.append(candidate)
        else:
            live.append(candidate)
        if len(dead) + len(live) >= k:
            break

    total = len(dead) + len(live)
    fraction = (len(dead) / float(total)) if total else 0.0
    return GhostNeighbourhood(
        query_id=int(query_id),
        dead_neighbours=tuple(dead),
        live_neighbours=tuple(live),
        blocked_fraction=fraction,
        available=True,
        unavailable_reason=None,
    )
