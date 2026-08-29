"""P1-02: IndexAdapter protocol and shared adapter helpers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from vhecfsck.adapters.base import (
    DENIED_WRITE_NAMES,
    FloatMatrix,
    IdArray,
    IndexAdapter,
    SearchParams,
    StringIdMapper,
    iter_vector_batches,
    l2_normalize,
)
from vhecfsck.models import (
    Capabilities,
    GraphStats,
    IndexCounts,
    IndexKind,
    MetricSpace,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> TargetDescriptor:
    return TargetDescriptor(
        engine="stub",
        engine_version="0",
        index_kind=IndexKind.FLAT,
        index_name="t",
        location="file:///tmp/t",
        dimension=2,
        metric_space=MetricSpace.L2,
    )


def _counts() -> IndexCounts:
    return IndexCounts(
        live=1,
        deleted=0,
        total=1,
        indexed=1,
        degenerate=0,
        exact=True,
        read_at=datetime(2026, 8, 29, tzinfo=UTC),
    )


class _ConformingStub:
    """Minimal structural IndexAdapter."""

    @property
    def descriptor(self) -> TargetDescriptor:
        return _descriptor()

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities()

    @property
    def dimension(self) -> int:
        return 2

    @property
    def metric_space(self) -> MetricSpace:
        return MetricSpace.L2

    def counts(self) -> IndexCounts:
        return _counts()

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        del batch_size
        ids = np.array([0], dtype=np.int64)
        vectors = np.zeros((1, 2), dtype=np.float32)
        yield VectorBatch(ids=ids, vectors=vectors)

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        del seed
        return np.arange(n, dtype=np.int64)

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        vectors = np.zeros((ids.shape[0], 2), dtype=np.float32)
        return VectorBatch(ids=ids.astype(np.int64, copy=False), vectors=vectors)

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        q = queries.shape[0]
        ids = np.full((q, k), -1, dtype=np.int64)
        return SearchResult(ids=ids, distances=None, effective_params=dict(params))

    def partitions(self) -> PartitionStats | None:
        return None

    def graph_stats(self) -> GraphStats | None:
        return None

    def close(self) -> None:
        return None


class _MissingCloseStub(_ConformingStub):
    close = None  # type: ignore[assignment]


def test_conforming_stub_is_index_adapter() -> None:
    stub = _ConformingStub()
    assert isinstance(stub, IndexAdapter)


def test_stub_missing_method_is_not_index_adapter() -> None:
    stub = _MissingCloseStub()
    assert not isinstance(stub, IndexAdapter)


def test_protocol_has_no_write_method_names() -> None:
    names = {n for n in dir(IndexAdapter) if not n.startswith("_")}
    overlap = names & DENIED_WRITE_NAMES
    assert not overlap, f"write names on IndexAdapter: {sorted(overlap)}"


def test_denied_write_names_match_readonly_guard() -> None:
    """Keep protocol denylist aligned with scripts/check_readonly.py."""
    import importlib.util

    path = ROOT / "scripts" / "check_readonly.py"
    spec = importlib.util.spec_from_file_location("check_readonly", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert DENIED_WRITE_NAMES == mod.DENIED_ATTRS


def test_optional_reads_return_none_when_capability_absent() -> None:
    stub = _ConformingStub()
    assert stub.capabilities.report_partitions is False
    assert stub.capabilities.report_graph_stats is False
    assert stub.partitions() is None
    assert stub.graph_stats() is None


def test_search_params_all_optional_and_echoed() -> None:
    stub = _ConformingStub()
    empty: SearchParams = {}
    result = stub.search(np.zeros((1, 2), dtype=np.float32), 3, params=empty)
    assert result.effective_params == {}
    full: SearchParams = {
        "nprobe": 16,
        "ef_search": 64,
        "refine_factor": 1.5,
        "exact": True,
    }
    result2 = stub.search(np.zeros((2, 2), dtype=np.float32), 1, params=full)
    assert result2.effective_params == dict(full)


def test_l2_normalize_unit_rows_and_contiguity() -> None:
    raw = np.array([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32)
    out = l2_normalize(raw)
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]
    norms = np.linalg.norm(out, axis=1)
    assert np.all(np.abs(norms - 1.0) < 1e-4)


def test_l2_normalize_rejects_zero_norm() -> None:
    raw = np.array([[0.0, 0.0]], dtype=np.float32)
    with pytest.raises(ValueError, match="zero-norm"):
        l2_normalize(raw)


def test_string_id_mapper_dense_stable() -> None:
    mapper = StringIdMapper()
    a = mapper.encode(["b", "a", "b"])
    assert a.dtype == np.int64
    assert a.tolist() == [0, 1, 0]
    b = mapper.encode(["a", "c"])
    assert b.tolist() == [1, 2]
    assert mapper.decode(np.array([0, 2, 1], dtype=np.int64)) == ["b", "c", "a"]


def test_iter_vector_batches() -> None:
    ids = np.arange(5, dtype=np.int64)
    vectors = np.eye(5, 2, dtype=np.float32)
    batches = list(iter_vector_batches(ids, vectors, batch_size=2))
    assert len(batches) == 3
    assert batches[0].ids.tolist() == [0, 1]
    assert batches[-1].ids.tolist() == [4]
    assert all(isinstance(b, VectorBatch) for b in batches)
