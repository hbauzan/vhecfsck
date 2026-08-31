"""Integration tests for P5-03: Exact deletion accounting in LanceDB."""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter


def test_deletion_accounting() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )
    vecs = np.random.randn(10, 4).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(10))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )

    ds = lance.write_dataset(data, tmp)
    # Delete 3 rows
    ds.delete("id IN (1, 3, 5)")

    adapter = LanceDBAdapter(tmp)
    try:
        counts = adapter.counts()
        assert counts.total == 10
        assert counts.deleted == 3
        assert counts.live == 7
        assert counts.exact is True
    finally:
        adapter.close()
