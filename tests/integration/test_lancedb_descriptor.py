"""Integration tests for P5-01: LanceDB dataset discovery and descriptor."""

from __future__ import annotations

import tempfile

import numpy as np
import pyarrow as pa
import pytest
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.errors import UsageError
from vhecfsck.models import IndexKind, MetricSpace


def create_sample_dataset(tmp_dir: str, d: int = 4, n: int = 20) -> str:
    import lance

    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), d)),
        ]
    )
    vecs = np.random.randn(n, d).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(n))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float32(), d)),
        ],
        schema=schema,
    )
    lance.write_dataset(data, tmp_dir)
    return tmp_dir


def test_lancedb_descriptor_flat() -> None:
    tmp = tempfile.mkdtemp()
    create_sample_dataset(tmp, d=4, n=20)

    adapter = LanceDBAdapter(tmp)
    try:
        desc = adapter.descriptor
        assert desc.engine == "lancedb"
        assert desc.index_kind == IndexKind.FLAT
        assert adapter.dimension == 4
        assert adapter.metric_space in (
            MetricSpace.L2,
            MetricSpace.COSINE,
            MetricSpace.DOT,
        )
        assert adapter.capabilities.report_deleted_counts is True
        assert adapter.capabilities.deleted_counts_exact is True
        assert adapter.capabilities.report_partitions is False
    finally:
        adapter.close()


def test_lancedb_descriptor_ivf_index() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    create_sample_dataset(tmp, d=4, n=100)
    ds = lance.dataset(tmp)
    ds.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        num_partitions=2,
    )

    adapter = LanceDBAdapter(tmp)
    try:
        desc = adapter.descriptor
        assert desc.engine == "lancedb"
        assert desc.index_kind == IndexKind.IVF
        assert adapter.metric_space == MetricSpace.L2
        assert adapter.capabilities.report_partitions is True
    finally:
        adapter.close()


def test_ambiguous_vector_columns_raises_error() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("vec1", pa.list_(pa.float32(), 4)),
            ("vec2", pa.list_(pa.float32(), 4)),
        ]
    )
    data = pa.Table.from_arrays(
        [
            pa.array([[1.0, 0.0, 0.0, 0.0]], type=pa.list_(pa.float32(), 4)),
            pa.array([[0.0, 1.0, 0.0, 0.0]], type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )
    lance.write_dataset(data, tmp)

    with pytest.raises(UsageError, match="Multiple vector columns"):
        LanceDBAdapter(tmp)

    adapter = LanceDBAdapter(tmp, column="vec2")
    assert adapter.dimension == 4
    adapter.close()
