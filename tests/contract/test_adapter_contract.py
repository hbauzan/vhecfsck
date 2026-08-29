"""Shared IndexAdapter contract suite — definition of a working adapter.

Parametrised over fixtures registered in ``conftest.ADAPTER_REGISTRY``.
Adding an engine = register a factory there; do not edit this module.
Zero skips by design: unsupported capabilities are asserted as ``None`` /
UNAVAILABLE, never skipped.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from tests.contract.conftest import (
    ADAPTER_REGISTRY,
    UNAVAILABLE_FROM_MISSING_CAPABILITY,
)
from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.errors import UsageError
from vhecfsck.models import (
    IndexCounts,
    PartitionStats,
    SearchResult,
    VectorBatch,
)


def _live_id_set(adapter: IndexAdapter) -> set[int]:
    found: set[int] = set()
    for batch in adapter.iter_live_vectors(batch_size=32):
        for i in range(batch.ids.shape[0]):
            found.add(int(batch.ids[i]))
    return found


def _count_fields(c: IndexCounts) -> tuple[int, int, int, int, int, bool]:
    """Observable cardinality — excludes wall-clock ``read_at``."""
    return (c.live, c.deleted, c.total, c.indexed, c.degenerate, c.exact)


def test_isinstance_index_adapter(adapter: IndexAdapter) -> None:
    assert isinstance(adapter, IndexAdapter)


def test_dimension_and_metric_stable_and_match_vectors(adapter: IndexAdapter) -> None:
    d = adapter.dimension
    metric = adapter.metric_space
    assert adapter.dimension == d
    assert adapter.metric_space is metric
    assert adapter.descriptor.dimension == d
    assert adapter.descriptor.metric_space is metric
    n_seen = 0
    for batch in adapter.iter_live_vectors(batch_size=16):
        assert isinstance(batch, VectorBatch)
        assert batch.vectors.dtype == np.float32
        assert batch.vectors.ndim == 2
        assert batch.vectors.shape[1] == d
        assert batch.ids.dtype == np.int64
        n_seen += int(batch.ids.shape[0])
    assert n_seen == adapter.counts().live


def test_iter_live_vectors_exact_unique_live_ids(adapter: IndexAdapter) -> None:
    live = adapter.counts().live
    ids = _live_id_set(adapter)
    assert len(ids) == live
    # Second pass: same cardinality (order may differ).
    assert len(_live_id_set(adapter)) == live


def test_sample_ids_deterministic_unique_live(adapter: IndexAdapter) -> None:
    live = adapter.counts().live
    a = adapter.sample_ids(50, seed=99)
    b = adapter.sample_ids(50, seed=99)
    assert a.tobytes() == b.tobytes()
    assert a.dtype == np.int64
    assert a.shape[0] == min(50, live)
    assert len({int(x) for x in a}) == a.shape[0]
    live_ids = _live_id_set(adapter)
    for x in a:
        assert int(x) in live_ids


def test_fetch_vectors_order_and_round_trip(adapter: IndexAdapter) -> None:
    live_map: dict[int, bytes] = {}
    for batch in adapter.iter_live_vectors(batch_size=24):
        for i in range(batch.ids.shape[0]):
            live_map[int(batch.ids[i])] = batch.vectors[i].tobytes()
    if not live_map:
        return
    ids = adapter.sample_ids(min(12, len(live_map)), seed=3)
    fetched = adapter.fetch_vectors(ids)
    assert isinstance(fetched, VectorBatch)
    assert fetched.ids.tobytes() == ids.tobytes()
    for i in range(ids.shape[0]):
        assert fetched.vectors[i].tobytes() == live_map[int(ids[i])]


def test_search_respects_k_padding_live_only_echoes_params(
    adapter: IndexAdapter,
) -> None:
    live_ids = _live_id_set(adapter)
    assert live_ids
    # Build queries from live vectors via fetch.
    sample = adapter.sample_ids(min(5, len(live_ids)), seed=21)
    queries = adapter.fetch_vectors(sample).vectors
    k = 7
    params = {"nprobe": 2, "ef_search": 16}
    result = adapter.search(queries, k, params=params)
    assert isinstance(result, SearchResult)
    assert result.ids.shape == (queries.shape[0], k)
    assert result.ids.dtype == np.int64
    assert "nprobe" in result.effective_params
    assert "ef_search" in result.effective_params
    assert result.effective_params["nprobe"] == 2
    assert result.effective_params["ef_search"] == 16
    for qi in range(result.ids.shape[0]):
        row = result.ids[qi]
        seen_pad = False
        for j in range(k):
            vid = int(row[j])
            if vid < 0:
                assert vid == -1
                seen_pad = True
            else:
                assert not seen_pad, "padding must be trailing"
                assert vid in live_ids


def test_capability_honesty_none_means_unavailable(adapter: IndexAdapter) -> None:
    caps = adapter.capabilities
    if not caps.report_partitions:
        assert adapter.partitions() is None
        assert UNAVAILABLE_FROM_MISSING_CAPABILITY
    else:
        parts = adapter.partitions()
        assert parts is not None
        assert isinstance(parts, PartitionStats)
        assert parts.n_partitions == int(parts.sizes.shape[0])
    if not caps.report_graph_stats:
        assert adapter.graph_stats() is None
        assert UNAVAILABLE_FROM_MISSING_CAPABILITY
    else:
        assert adapter.graph_stats() is not None


def test_readonly_audit_sequence_preserves_counts(adapter: IndexAdapter) -> None:
    before = _count_fields(adapter.counts())
    _ = adapter.descriptor
    _ = adapter.capabilities
    _ = adapter.dimension
    _ = adapter.metric_space
    live = _live_id_set(adapter)
    sample = adapter.sample_ids(min(8, max(1, len(live))), seed=5)
    _ = adapter.fetch_vectors(sample)
    if live:
        q = adapter.fetch_vectors(sample[:1]).vectors
        _ = adapter.search(q, 5, params={"nprobe": 1, "ef_search": 8})
    _ = adapter.partitions()
    _ = adapter.graph_stats()
    after = _count_fields(adapter.counts())
    assert before == after


def test_close_idempotent_and_blocks_use(adapter: IndexAdapter) -> None:
    adapter.close()
    adapter.close()
    with pytest.raises((UsageError, RuntimeError, ValueError)):
        adapter.counts()


def test_registry_is_nonempty_and_suite_has_no_skips() -> None:
    assert ADAPTER_REGISTRY, "register at least SyntheticAdapter"
    # Build needles without embedding the literal call forms in this file's body
    # in a way that would self-match a naive substring scan.
    needles = (
        "pytest" + ".skip(",
        "pytest" + ".mark.skip",
        "pytest" + ".mark.xfail",
    )
    root = Path(__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{path.name} contains {needle!r}"
