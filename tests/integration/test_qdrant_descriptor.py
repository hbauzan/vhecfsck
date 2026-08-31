"""Qdrant descriptor tests against the embedded client (P7-02)."""

from __future__ import annotations

import pytest
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.models import IndexKind, MetricSpace

pytest.importorskip("qdrant_client")

pytestmark = [pytest.mark.integration, pytest.mark.requires_qdrant]


@pytest.mark.parametrize(
    ("distance_name", "expected"),
    [
        ("COSINE", MetricSpace.COSINE),
        ("EUCLID", MetricSpace.L2),
        ("DOT", MetricSpace.DOT),
    ],
)
def test_qdrant_descriptor_metric_spaces(
    distance_name: str, expected: MetricSpace
) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    distance = getattr(models.Distance, distance_name)
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="metric_col",
        vectors_config=models.VectorParams(size=4, distance=distance),
    )
    client.upsert(
        collection_name="metric_col",
        points=[models.PointStruct(id=0, vector=[0.1, 0.2, 0.3, 0.4])],
    )
    adapter = QdrantAdapter("qdrant://memory/metric_col", client=client)
    try:
        desc = adapter.descriptor
        assert desc.engine == "qdrant"
        assert desc.index_kind is IndexKind.HNSW
        assert desc.metric_space is expected
        assert adapter.dimension == 4
        assert adapter.transport == "injected"
    finally:
        adapter.close()
