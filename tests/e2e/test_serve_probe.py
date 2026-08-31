"""E2E: interactive probe against a live synthetic adapter (P6-03)."""

from __future__ import annotations

import numpy as np
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.models import VectorBatch
from vhecfsck.server.probe_service import run_probe, run_probe_bundle


def test_probe_ground_truth_matches_core_ground_truth() -> None:
    opened = open_scenario("tombstoned", size="tiny")
    try:
        blocks = list(opened.adapter.iter_live_vectors(batch_size=50_000))
        corpus = VectorBatch(
            ids=np.concatenate([b.ids for b in blocks]),
            vectors=np.ascontiguousarray(
                np.concatenate([b.vectors for b in blocks], axis=0), dtype=np.float32
            ),
        )
        query_id = int(corpus.ids[4])
        row = int(np.flatnonzero(corpus.ids == query_id)[0])
        result = run_probe(opened.adapter, query_id=query_id, k=5)
        oracle = exact_knn(
            [corpus],
            corpus.vectors[row : row + 1],
            6,
            opened.adapter.metric_space,
            n_total=int(corpus.ids.shape[0]),
        )
        expected = [
            int(oracle.ids[0, c])
            for c in range(int(oracle.ids.shape[1]))
            if int(oracle.ids[0, c]) not in (-1, query_id)
        ][:5]
        assert list(result.true_neighbours) == expected
    finally:
        opened.adapter.close()


def test_tombstoned_probe_bundle_is_usable() -> None:
    opened = open_scenario("tombstoned", size="tiny")
    try:
        blocks = list(opened.adapter.iter_live_vectors(batch_size=50_000))
        query_id = int(blocks[0].ids[0])
        payload = run_probe_bundle(opened.adapter, query_id=query_id, k=5)
        assert payload["available"] is True
        assert payload["missed"] is not None
        assert "dead_returns" in payload
    finally:
        opened.adapter.close()
