"""Integration tests for P5-06: LanceDB IVF partition introspection."""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter


def test_ivf_partitions() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )
    vecs = np.random.randn(100, 4).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(100))),
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
        parts = adapter.partitions()
        assert parts is not None
        assert parts.n_partitions == 4
        assert len(parts.sizes) == 4
        assert parts.sizes.sum() == 100
        assert parts.includes_deleted is True
    finally:
        adapter.close()


def test_non_ivf_returns_none() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )
    vecs = np.random.randn(20, 4).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(20))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )

    lance.write_dataset(data, tmp)

    adapter = LanceDBAdapter(tmp)
    try:
        assert adapter.partitions() is None
    finally:
        adapter.close()
