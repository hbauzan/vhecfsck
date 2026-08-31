"""Integration tests for P5-02: LanceDB snapshot version pinning."""

from __future__ import annotations

import tempfile

import pyarrow as pa
import pytest
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.errors import UsageError


def test_version_pinning_consistency() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )

    vec_a = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    data1 = pa.Table.from_arrays(
        [
            pa.array([1, 2]),
            pa.array(vec_a, type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )
    ds = lance.write_dataset(data1, tmp)
    v1 = ds.version

    # Open adapter pinned to v1
    adapter1 = LanceDBAdapter(tmp, dataset_version=v1)
    assert adapter1.counts().live == 2

    # Mutate dataset (append 2 rows) -> version 2
    vec_b = [[0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    data2 = pa.Table.from_arrays(
        [
            pa.array([3, 4]),
            pa.array(vec_b, type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )
    lance.write_dataset(data2, tmp, mode="append")

    # adapter1 pinned to v1 should still see live count == 2!
    assert adapter1.counts().live == 2
    adapter1.close()

    # New adapter without explicit version picks latest (v2, live=4)
    adapter2 = LanceDBAdapter(tmp)
    assert adapter2.counts().live == 4
    adapter2.close()


def test_invalid_dataset_version_raises_usage_error() -> None:
    import lance

    tmp = tempfile.mkdtemp()
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 4)),
        ]
    )
    data = pa.Table.from_arrays(
        [
            pa.array([1]),
            pa.array([[1.0, 0.0, 0.0, 0.0]], type=pa.list_(pa.float32(), 4)),
        ],
        schema=schema,
    )
    lance.write_dataset(data, tmp)

    with pytest.raises(UsageError, match="version"):
        LanceDBAdapter(tmp, dataset_version=9999)


def test_version_compatibility_checker() -> None:
    from vhecfsck.adapters.lancedb_adapter import (
        _parse_version_tuple,
        check_lancedb_version_compatibility,
    )

    assert _parse_version_tuple("0.11.0") == (0, 11, 0)
    assert _parse_version_tuple("11.0.0-beta1") == (11, 0, 0)
    assert _parse_version_tuple("0.37.1.dev0") == (0, 37, 1)

    # In-range
    assert check_lancedb_version_compatibility("11.0.0", "0.37.1") is None

    # Out of range lance
    warn_lance = check_lancedb_version_compatibility("0.1.0", "0.37.1")
    assert warn_lance is not None and "Lance version" in warn_lance

    # Out of range lancedb
    warn_ldb = check_lancedb_version_compatibility("11.0.0", "0.0.1")
    assert warn_ldb is not None and "LanceDB version" in warn_ldb
