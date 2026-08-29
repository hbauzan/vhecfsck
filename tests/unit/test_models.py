"""P1-01: shared domain types (leaf models package)."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from vhecfsck.logging import redact_secrets
from vhecfsck.models.corpus import (
    GraphStats,
    IndexCounts,
    PartitionStats,
    SearchResult,
    VectorBatch,
)
from vhecfsck.models.target import (
    Capabilities,
    IndexKind,
    MetricSpace,
    TargetDescriptor,
)

ROOT = Path(__file__).resolve().parents[2]


def test_metric_space_values() -> None:
    assert set(MetricSpace) == {
        MetricSpace.COSINE,
        MetricSpace.L2,
        MetricSpace.DOT,
    }
    assert MetricSpace.COSINE.value == "COSINE"


def test_index_kind_values() -> None:
    assert set(IndexKind) == {
        IndexKind.FLAT,
        IndexKind.IVF,
        IndexKind.IVF_PQ,
        IndexKind.HNSW,
        IndexKind.HNSW_PQ,
        IndexKind.UNKNOWN,
    }


def test_capabilities_default_all_false() -> None:
    caps = Capabilities()
    assert caps.enumerate_vectors is False
    assert caps.random_access_by_id is False
    assert caps.report_deleted_counts is False
    assert caps.deleted_counts_exact is False
    assert caps.report_partitions is False
    assert caps.partition_live_counts is False
    assert caps.report_graph_stats is False
    assert caps.search_params_settable is False
    assert caps.filtered_search is False


def test_capabilities_frozen_and_hashable() -> None:
    a = Capabilities(enumerate_vectors=True)
    b = Capabilities(enumerate_vectors=True)
    with pytest.raises(FrozenInstanceError):
        a.enumerate_vectors = False  # type: ignore[misc]
    assert hash(a) == hash(b)
    assert {a: "ok"}[b] == "ok"


def test_target_descriptor_frozen_and_hashable() -> None:
    desc = TargetDescriptor(
        engine="synthetic",
        engine_version="0.0.0",
        index_kind=IndexKind.FLAT,
        index_name="demo",
        location="file:///tmp/demo.lance",
        dimension=8,
        metric_space=MetricSpace.COSINE,
    )
    with pytest.raises(FrozenInstanceError):
        desc.dimension = 16  # type: ignore[misc]
    assert hash(desc) == hash(
        TargetDescriptor(
            engine="synthetic",
            engine_version="0.0.0",
            index_kind=IndexKind.FLAT,
            index_name="demo",
            location="file:///tmp/demo.lance",
            dimension=8,
            metric_space=MetricSpace.COSINE,
        )
    )


def test_target_descriptor_location_via_redact_secrets() -> None:
    raw = "postgres://alice:s3cret@db.example:5432/vectors"
    desc = TargetDescriptor(
        engine="pgvector",
        engine_version="0.7.0",
        index_kind=IndexKind.HNSW,
        index_name="idx",
        location=redact_secrets(raw),
        dimension=768,
        metric_space=MetricSpace.L2,
    )
    assert "s3cret" not in desc.location
    assert "REDACTED" in desc.location


def test_index_counts_frozen() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    counts = IndexCounts(
        live=10,
        deleted=2,
        total=12,
        indexed=10,
        degenerate=0,
        exact=True,
        read_at=now,
    )
    assert counts.live == 10
    with pytest.raises(FrozenInstanceError):
        counts.live = 0  # type: ignore[misc]
    assert hash(counts) == hash(
        IndexCounts(
            live=10,
            deleted=2,
            total=12,
            indexed=10,
            degenerate=0,
            exact=True,
            read_at=now,
        )
    )


@pytest.mark.parametrize(
    ("ids", "vectors", "match"),
    [
        (
            np.array([0, 1], dtype=np.int64),
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64),
            "float32",
        ),
        (
            np.array([0, 1], dtype=np.int64),
            np.asfortranarray(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)),
            "C-contiguous",
        ),
        (
            np.array([0, 1], dtype=np.int64),
            np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32),
            "rank",
        ),
        (
            np.array([0, 1, 2], dtype=np.int64),
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            "length",
        ),
        (
            np.array([0, 1], dtype=np.int32),
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            "int64",
        ),
        (
            np.array([[0], [1]], dtype=np.int64),
            np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            "rank",
        ),
    ],
)
def test_vector_batch_rejects_invalid(
    ids: np.ndarray,
    vectors: np.ndarray,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        VectorBatch(ids=ids, vectors=vectors)


def test_vector_batch_accepts_valid() -> None:
    ids = np.array([3, 1], dtype=np.int64)
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    batch = VectorBatch(ids=ids, vectors=vectors)
    assert batch.ids.dtype == np.int64
    assert batch.vectors.dtype == np.float32
    assert batch.vectors.flags["C_CONTIGUOUS"]
    assert batch.vectors.shape == (2, 2)


def test_search_result_and_partition_graph_shapes() -> None:
    result = SearchResult(
        ids=np.array([[1, 2, -1], [3, -1, -1]], dtype=np.int64),
        distances=None,
        effective_params={"nprobe": 8},
    )
    assert result.ids.shape == (2, 3)
    assert result.distances is None

    parts = PartitionStats(
        sizes=np.array([4, 6], dtype=np.int64),
        includes_deleted=False,
        n_partitions=2,
    )
    assert parts.n_partitions == 2

    graph = GraphStats(
        in_degree_histogram=np.array([0, 3, 1], dtype=np.int64),
        entry_point_ids=np.array([0], dtype=np.int64),
        entrypoint_tombstoned=False,
    )
    assert graph.entrypoint_tombstoned is False


def test_models_corpus_imports_no_internal_packages() -> None:
    """Acceptance: import graph of models.corpus stays a leaf."""
    corpus_path = ROOT / "vhecfsck" / "models" / "corpus.py"
    target_path = ROOT / "vhecfsck" / "models" / "target.py"
    forbidden_roots = (
        "vhecfsck.core",
        "vhecfsck.adapters",
        "vhecfsck.server",
        "vhecfsck.cli",
        "vhecfsck.config",
        "vhecfsck.errors",
        "vhecfsck.logging",
        "vhecfsck.report",
    )
    for path in (corpus_path, target_path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_roots:
                        assert not alias.name.startswith(forbidden), (
                            f"{path.name} imports {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                for forbidden in forbidden_roots:
                    assert not node.module.startswith(forbidden), (
                        f"{path.name} imports from {node.module}"
                    )
