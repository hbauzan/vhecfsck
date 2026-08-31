"""Integration tests for P5-04: LanceDB vector streaming and random access."""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter


def test_vector_streaming_and_upcast() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float16(), 4)),
        ]
    )
    vecs = np.random.randn(15, 4).astype(np.float16)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(15))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float16(), 4)),
        ],
        schema=schema,
    )

    lance.write_dataset(data, tmp)

    adapter = LanceDBAdapter(tmp)
    try:
        batches = list(adapter.iter_live_vectors(batch_size=5))
        assert len(batches) == 3
        total_vectors = 0
        for b in batches:
            assert b.vectors.dtype == np.float32
            assert b.vectors.shape[1] == 4
            total_vectors += len(b.ids)
        assert total_vectors == 15

        # Test deterministic sample_ids
        sampled_ids = adapter.sample_ids(5, seed=42)
        assert len(sampled_ids) == 5

        # Test fetch_vectors
        fetched = adapter.fetch_vectors(sampled_ids)
        assert len(fetched.ids) == 5
        assert fetched.vectors.dtype == np.float32
        assert fetched.vectors.shape == (5, 4)
    finally:
        adapter.close()
