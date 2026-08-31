"""Qdrant counts, DFI honesty, and read-only audit sequence (P7-02)."""

from __future__ import annotations

import pytest
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.core.fragmentation import compute_dfi
from vhecfsck.models import MetricState

pytest.importorskip("qdrant_client")

pytestmark = pytest.mark.requires_qdrant


def test_clean_collection_dfi_never_spurious(qdrant_embedded_collection) -> None:
    client, name = qdrant_embedded_collection
    adapter = QdrantAdapter(f"qdrant://memory/{name}", client=client)
    try:
        counts = adapter.counts()
        assert counts.live == 24
        result = compute_dfi(
            counts,
            report_deleted_counts=adapter.capabilities.report_deleted_counts,
        )
        if adapter.capabilities.report_deleted_counts:
            assert result.value == pytest.approx(0.0)
            assert result.state is MetricState.OK
        else:
            assert result.state is MetricState.UNAVAILABLE
            assert result.value is None
        # The telemetry trap: indexed gap is not a tombstone count.
        info = client.get_collection(name)
        indexed = getattr(info, "indexed_vectors_count", None)
        points = getattr(info, "points_count", None)
        if (
            indexed is not None
            and points is not None
            and int(indexed) != int(points)
            and not adapter.capabilities.report_deleted_counts
        ):
            assert counts.deleted != int(points) - int(indexed)
    finally:
        adapter.close()


def test_point_and_payload_counts(qdrant_embedded_collection) -> None:
    client, name = qdrant_embedded_collection
    adapter = QdrantAdapter(f"qdrant://memory/{name}", client=client)
    try:
        assert adapter.counts().live == 24
        assert "i" in adapter.payload_fields or adapter.payload_fields == ()
        n_seen = 0
        for batch in adapter.iter_live_vectors(batch_size=7):
            n_seen += int(batch.ids.shape[0])
        assert n_seen == 24
    finally:
        adapter.close()


def test_readonly_audit_leaves_counts_unchanged(qdrant_embedded_collection) -> None:
    client, name = qdrant_embedded_collection
    adapter = QdrantAdapter(f"qdrant://memory/{name}", client=client)
    try:
        before = adapter.counts()
        sample = adapter.sample_ids(5, seed=3)
        fetched = adapter.fetch_vectors(sample)
        _ = adapter.search(
            fetched.vectors[:1], 4, params={"ef_search": 16, "nprobe": 1}
        )
        after = adapter.counts()
        assert (before.live, before.deleted, before.total, before.indexed) == (
            after.live,
            after.deleted,
            after.total,
            after.indexed,
        )
        result = client.count(name, exact=True)
        assert int(result.count) == 24
    finally:
        adapter.close()
