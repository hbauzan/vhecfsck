"""Single-query probe: the comparison that makes a retrieval failure legible.

P6-03. For one point, this module answers four questions the aggregate metrics
can only summarise: which neighbours are truly nearest, which ones the engine
returned, which true neighbours it *missed*, and which ids it returned that no
longer exist. Ground truth comes from :func:`vhecfsck.core.ground_truth.exact_knn`
— the same oracle the canary metric is scored against, so a probe can never
disagree with the report.

Self-exclusion is symmetric (the query's own id is dropped from ground truth
*and* from the engine row) because a self-match at distance zero would otherwise
inflate the comparison for free.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import MetricSpace, VectorBatch

#: Cap on the query list returned by the inverse hub view, so one pathological
#: hub cannot return a hundred thousand ids to the browser.
MAX_CANNIBALISED_QUERIES = 500


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of probing one point.

    Attributes:
        query_id: Corpus id used as the query.
        k: Neighbours requested, after self-exclusion.
        true_neighbours: Ground-truth ids, nearest first.
        true_distances: Distances matching ``true_neighbours``.
        engine_returned: Ids the engine returned, in its own order.
        missed: True neighbours the engine did not return — the failure.
        dead_returns: Ids the engine returned that are not live in the
            snapshot; rendered struck through.
        unexpected: Live ids the engine returned that are not true neighbours.
        n_k: In-degree of the probed point, when hubness supplied it.
        recall_id: Fraction of true neighbours the engine returned.
        available: False when the probe could not run.
        unavailable_reason: Why the probe could not run, or None.
    """

    query_id: int
    k: int
    true_neighbours: tuple[int, ...]
    true_distances: tuple[float, ...]
    engine_returned: tuple[int, ...]
    missed: tuple[int, ...]
    dead_returns: tuple[int, ...]
    unexpected: tuple[int, ...]
    n_k: int | None
    recall_id: float
    available: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class HubCannibalisation:
    """Inverse view of a hub: the queries that land on it.

    Attributes:
        hub_id: The point being cannibalised onto.
        n_k: How many sampled queries reached it, before the display cap.
        query_ids: Ids of those queries, ascending, capped for transport.
        truncated: True when ``query_ids`` was capped.
    """

    hub_id: int
    n_k: int
    query_ids: tuple[int, ...]
    truncated: bool


def _materialise(
    batches: Iterable[VectorBatch],
) -> tuple[NDArray[np.int64], NDArray[np.float32], dict[int, int]]:
    collected = list(batches)
    if not collected:
        return (
            np.empty(0, dtype=np.int64),
            np.zeros((0, 0), dtype=np.float32),
            {},
        )
    ids = np.concatenate([b.ids for b in collected]).astype(np.int64, copy=False)
    vectors = np.concatenate([b.vectors for b in collected], axis=0)
    index: dict[int, int] = {}
    for row in range(int(ids.shape[0])):
        index[int(ids[row])] = row
    return ids, np.ascontiguousarray(vectors, dtype=np.float32), index


def _unavailable(query_id: int, k: int, reason: str) -> ProbeResult:
    return ProbeResult(
        query_id=query_id,
        k=k,
        true_neighbours=(),
        true_distances=(),
        engine_returned=(),
        missed=(),
        dead_returns=(),
        unexpected=(),
        n_k=None,
        recall_id=0.0,
        available=False,
        unavailable_reason=reason,
    )


def probe_point(
    *,
    query_id: int,
    corpus_batches: Iterable[VectorBatch],
    returned_ids: Sequence[int] | NDArray[np.integer],
    metric_space: MetricSpace,
    k: int,
    n_k: int | None = None,
    working_set_mb: float = 256.0,
) -> ProbeResult:
    """Compare exact neighbours against what the engine returned for one point.

    Args:
        query_id: Corpus id to probe. Must be live in the snapshot.
        corpus_batches: Live corpus, streamed as batches.
        returned_ids: Ids the engine returned for this query, in its order.
            Negative entries are treated as padding.
        metric_space: Distance space the index was built in.
        k: Neighbours to compare, excluding the query itself.
        n_k: In-degree from the hubness pass, when available.
        working_set_mb: Blocking budget handed to the ground-truth pass.

    Returns:
        A :class:`ProbeResult`. Probing an id that is no longer live returns
        ``available=False`` with a reason rather than raising, so a point
        deleted mid-session degrades gracefully.

    Raises:
        ValueError: If ``k`` is below one.
    """
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)

    ids, vectors, id_to_row = _materialise(corpus_batches)
    n_live = int(ids.shape[0])
    if n_live == 0:
        return _unavailable(query_id, k, "the live corpus is empty")

    row = id_to_row.get(int(query_id))
    if row is None:
        return _unavailable(
            query_id,
            k,
            f"vector {query_id} is not live in this snapshot; it may have been "
            "deleted since the scene was built",
        )

    # k+1 because the query matches itself at distance zero.
    gt = exact_knn(
        [VectorBatch(ids=ids, vectors=vectors)],
        vectors[row : row + 1],
        min(k + 1, n_live),
        metric_space,
        working_set_mb=working_set_mb,
        n_total=n_live,
    )

    true_ids: list[int] = []
    true_dists: list[float] = []
    for column in range(int(gt.ids.shape[1])):
        candidate = int(gt.ids[0, column])
        if candidate < 0 or candidate == int(query_id):
            continue
        true_ids.append(candidate)
        true_dists.append(float(gt.distances[0, column]))
        if len(true_ids) >= k:
            break

    engine: list[int] = []
    seen: dict[int, None] = {}
    for raw in returned_ids:
        value = int(raw)
        if value < 0 or value == int(query_id) or value in seen:
            continue
        seen[value] = None
        engine.append(value)

    true_set = set(true_ids)
    engine_set = set(engine)
    dead = [rid for rid in engine if rid not in id_to_row]
    dead_set = set(dead)

    missed = [tid for tid in true_ids if tid not in engine_set]
    unexpected = [rid for rid in engine if rid not in true_set and rid not in dead_set]

    denominator = len(true_ids)
    hits = denominator - len(missed)
    recall = (hits / float(denominator)) if denominator else 0.0

    return ProbeResult(
        query_id=int(query_id),
        k=k,
        true_neighbours=tuple(true_ids),
        true_distances=tuple(true_dists),
        engine_returned=tuple(engine),
        missed=tuple(missed),
        dead_returns=tuple(dead),
        unexpected=tuple(unexpected),
        n_k=n_k,
        recall_id=recall,
        available=True,
        unavailable_reason=None,
    )


def hub_cannibalisation(
    *,
    hub_id: int,
    neighbour_ids: NDArray[np.int64],
    query_ids: NDArray[np.int64],
    cap: int = MAX_CANNIBALISED_QUERIES,
) -> HubCannibalisation:
    """List the sampled queries whose neighbourhood contains ``hub_id``.

    This is the view that makes hubness intuitive without a definition: one
    point with lines to hundreds of unrelated queries explains itself.

    Args:
        hub_id: The point to invert.
        neighbour_ids: ``(Q, k)`` neighbour matrix from the hubness pass.
        query_ids: ``(Q,)`` ids of the queries in that matrix.
        cap: Maximum ids to return.

    Returns:
        A :class:`HubCannibalisation`. ``n_k`` is the uncapped count.

    Raises:
        ValueError: If the matrix and the query ids disagree in length.
    """
    matrix = np.asarray(neighbour_ids, dtype=np.int64)
    queries = np.asarray(query_ids, dtype=np.int64).reshape(-1)
    if matrix.ndim != 2:
        msg = f"neighbour_ids must be 2-D, got shape {matrix.shape}"
        raise ValueError(msg)
    if matrix.shape[0] != queries.shape[0]:
        msg = (
            f"neighbour_ids has {matrix.shape[0]} rows but query_ids has "
            f"{queries.shape[0]} entries"
        )
        raise ValueError(msg)

    hits = np.any(matrix == int(hub_id), axis=1)
    # Exclude a self-match: a point being its own neighbour is not cannibalism.
    hits &= queries != int(hub_id)
    matched = np.sort(queries[hits])

    total = int(matched.shape[0])
    truncated = total > cap
    return HubCannibalisation(
        hub_id=int(hub_id),
        n_k=total,
        query_ids=tuple(int(x) for x in matched[:cap]),
        truncated=truncated,
    )
