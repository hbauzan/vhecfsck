"""Integration tests for P5-05: LanceDB native k-NN search."""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
import pytest
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter


def test_search_flat_and_ivf() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )
    vecs = np.random.randn(50, 4).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(50))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )

    ds = lance.write_dataset(data, tmp)
    ds.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        num_partitions=4,
    )

    adapter = LanceDBAdapter(tmp)
    try:
        queries = vecs[:5]
        res = adapter.search(queries, k=3, params={"nprobe": 2})
        assert res.ids.shape == (5, 3)
        assert res.distances is not None
        assert res.distances.shape == (5, 3)
        assert "nprobe" in res.effective_params
        assert res.effective_params["nprobe"] == 2

        # First query top-1 self match distance should be ~0.0
        assert res.distances[0, 0] == pytest.approx(0.0, abs=1e-4)
    finally:
        adapter.close()
