"""Runs one interactive probe against a live adapter (P6-03).

Framework-free. The route is responsible for admission control and caching;
this module does the read and hands the arrays to ``core.probe``, which owns
every comparison.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from vhecfsck.core.probe import (
    HubCannibalisation,
    ProbeResult,
    hub_cannibalisation,
    probe_point,
)
from vhecfsck.models import VectorBatch

READ_BATCH = 50_000


def _read_corpus(adapter: Any) -> tuple[np.ndarray, np.ndarray]:
    id_blocks: list[np.ndarray] = []
    vector_blocks: list[np.ndarray] = []
    for batch in adapter.iter_live_vectors(batch_size=READ_BATCH):
        id_blocks.append(batch.ids)
        vector_blocks.append(batch.vectors)

    if not id_blocks:
        return np.empty(0, dtype=np.int64), np.zeros((0, 0), dtype=np.float32)

    return (
        np.concatenate(id_blocks),
        np.ascontiguousarray(np.concatenate(vector_blocks, axis=0), dtype=np.float32),
    )


def run_probe(
    adapter: Any,
    *,
    query_id: int,
    k: int,
    search_params: dict[str, Any] | None = None,
) -> ProbeResult:
    """Probe one corpus point and compare truth against the engine.

    Args:
        adapter: An open, read-only index adapter.
        query_id: Corpus id to probe.
        k: Neighbours to compare, excluding the query itself.
        search_params: Engine search parameters, passed through unchanged.

    Returns:
        A :class:`vhecfsck.core.probe.ProbeResult`. An id that is no longer
        live yields an unavailable result rather than an exception.
    """
    ids, vectors = _read_corpus(adapter)
    if ids.shape[0] == 0:
        return probe_point(
            query_id=query_id,
            corpus_batches=[],
            returned_ids=[],
            metric_space=adapter.metric_space,
            k=k,
        )

    matches = np.flatnonzero(ids == int(query_id))
    if matches.size == 0:
        # Let core produce the canonical "not live" result and reason.
        return probe_point(
            query_id=query_id,
            corpus_batches=[VectorBatch(ids=ids, vectors=vectors)],
            returned_ids=[],
            metric_space=adapter.metric_space,
            k=k,
        )

    row = int(matches[0])
    query = np.ascontiguousarray(vectors[row : row + 1], dtype=np.float32)
    # k+1 so the engine's own self-match does not consume a comparison slot.
    result = adapter.search(query, k + 1, params=search_params or {})

    return probe_point(
        query_id=query_id,
        corpus_batches=[VectorBatch(ids=ids, vectors=vectors)],
        returned_ids=[int(x) for x in np.asarray(result.ids).reshape(-1).tolist()],
        metric_space=adapter.metric_space,
        k=k,
    )


def _cannibalisation(adapter: Any, *, hub_id: int, k: int) -> HubCannibalisation | None:
    """Inverse view: which sampled queries the engine landed on ``hub_id``."""
    try:
        n_live = int(adapter.counts().live or 0)
    except (AttributeError, TypeError):
        return None
    sample_n = min(500, n_live)
    if sample_n < 2:
        return None
    sample_ids = adapter.sample_ids(sample_n, seed=1337)
    if int(sample_ids.shape[0]) < 2:
        return None
    batch = adapter.fetch_vectors(sample_ids)
    search = adapter.search(batch.vectors, k + 1, params={})
    return hub_cannibalisation(
        hub_id=hub_id,
        neighbour_ids=np.asarray(search.ids, dtype=np.int64),
        query_ids=batch.ids,
    )


def run_probe_bundle(
    adapter: Any,
    *,
    query_id: int,
    k: int,
    search_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Probe plus the inverse hub view, as the JSON object the browser gets."""
    result = run_probe(adapter, query_id=query_id, k=k, search_params=search_params)
    payload = probe_to_dict(result)
    payload["cannibalisation"] = None
    if result.available:
        view = _cannibalisation(adapter, hub_id=query_id, k=k)
        if view is not None:
            payload["cannibalisation"] = {
                "hub_id": view.hub_id,
                "n_k": view.n_k,
                "query_ids": list(view.query_ids),
                "truncated": view.truncated,
            }
    return payload


def probe_to_dict(result: ProbeResult) -> dict[str, Any]:
    """Render a probe result as the JSON object sent to the browser.

    Args:
        result: Result to serialise.

    Returns:
        A plain dict of JSON-safe values.
    """
    return {
        "query_id": result.query_id,
        "k": result.k,
        "true_neighbours": list(result.true_neighbours),
        "true_distances": [float(d) for d in result.true_distances],
        "engine_returned": list(result.engine_returned),
        "missed": list(result.missed),
        "dead_returns": list(result.dead_returns),
        "unexpected": list(result.unexpected),
        "n_k": result.n_k,
        "recall_id": result.recall_id,
        "available": result.available,
        "unavailable_reason": result.unavailable_reason,
    }
