"""Probe execution against a live synthetic adapter (P6-03)."""

from __future__ import annotations

import numpy as np
import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import VectorBatch
from vhecfsck.server.probe_service import probe_to_dict, run_probe, run_probe_bundle


@pytest.fixture(scope="module")
def tombstoned_adapter():
    opened = open_scenario("tombstoned", size="tiny")
    try:
        yield opened.adapter
    finally:
        close = getattr(opened.adapter, "close", None)
        if close is not None:
            close()


def _live_corpus(adapter) -> VectorBatch:
    blocks = list(adapter.iter_live_vectors(batch_size=50_000))
    return VectorBatch(
        ids=np.concatenate([b.ids for b in blocks]),
        vectors=np.ascontiguousarray(
            np.concatenate([b.vectors for b in blocks], axis=0), dtype=np.float32
        ),
    )


def test_probe_ground_truth_matches_the_oracle_for_the_same_point(
    tombstoned_adapter,
) -> None:
    """Probe and report cannot disagree: both go through exact_knn."""
    corpus = _live_corpus(tombstoned_adapter)
    query_id = int(corpus.ids[3])
    row = int(np.flatnonzero(corpus.ids == query_id)[0])

    result = run_probe(tombstoned_adapter, query_id=query_id, k=5)

    oracle = exact_knn(
        [corpus],
        corpus.vectors[row : row + 1],
        6,
        tombstoned_adapter.metric_space,
        n_total=int(corpus.ids.shape[0]),
    )
    expected = [
        int(oracle.ids[0, c])
        for c in range(int(oracle.ids.shape[1]))
        if int(oracle.ids[0, c]) not in (-1, query_id)
    ][:5]

    assert list(result.true_neighbours) == expected


def test_a_probe_on_a_tombstoned_scenario_returns_a_usable_comparison(
    tombstoned_adapter,
) -> None:
    corpus = _live_corpus(tombstoned_adapter)

    result = run_probe(tombstoned_adapter, query_id=int(corpus.ids[0]), k=5)

    assert result.available is True
    assert len(result.true_neighbours) == 5
    assert 0.0 <= result.recall_id <= 1.0
    assert set(result.missed) <= set(result.true_neighbours)


def test_the_engine_row_never_contains_the_query_itself(tombstoned_adapter) -> None:
    corpus = _live_corpus(tombstoned_adapter)
    query_id = int(corpus.ids[1])

    result = run_probe(tombstoned_adapter, query_id=query_id, k=5)

    assert query_id not in result.engine_returned
    assert query_id not in result.true_neighbours


def test_probing_a_dead_id_degrades_gracefully(tombstoned_adapter) -> None:
    result = run_probe(tombstoned_adapter, query_id=10_000_000, k=5)

    assert result.available is False
    assert result.unavailable_reason is not None


def test_probe_serialises_to_json_safe_primitives(tombstoned_adapter) -> None:
    corpus = _live_corpus(tombstoned_adapter)

    payload = probe_to_dict(
        run_probe(tombstoned_adapter, query_id=int(corpus.ids[2]), k=4)
    )

    assert isinstance(payload["true_neighbours"], list)
    assert all(isinstance(x, int) for x in payload["true_neighbours"])
    assert all(isinstance(x, float) for x in payload["true_distances"])
    assert payload["available"] is True


def test_probe_bundle_includes_the_inverse_hub_view(tombstoned_adapter) -> None:
    corpus = _live_corpus(tombstoned_adapter)
    payload = run_probe_bundle(tombstoned_adapter, query_id=int(corpus.ids[0]), k=5)

    assert payload["available"] is True
    assert payload["cannibalisation"] is not None
    assert payload["cannibalisation"]["hub_id"] == int(corpus.ids[0])
    assert "query_ids" in payload["cannibalisation"]
