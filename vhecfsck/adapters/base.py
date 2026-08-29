"""Read-only IndexAdapter protocol and shared adapter helpers.

Do not add write methods to IndexAdapter. Do not call engine write APIs
from any adapter. Every method on IndexAdapter is a pure read: never
create, update, remove, lock, compact, rebuild, or otherwise mutate the
target. If a capability is absent, optional reads return None — never
invent a substitute number.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol, TypedDict, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from vhecfsck.models import (
    Capabilities,
    GraphStats,
    IndexCounts,
    MetricSpace,
    PartitionStats,
    SearchResult,
    TargetDescriptor,
    VectorBatch,
)

# Aligned with scripts/check_readonly.DENIED_ATTRS — asserted in tests.
DENIED_WRITE_NAMES: frozenset[str] = frozenset(
    {
        "delete",
        "delete_by_filter",
        "upsert",
        "insert",
        "add",
        "merge_insert",
        "update",
        "drop",
        "create_index",
        "optimize",
        "compact",
        "cleanup_old_versions",
        "restore",
        "commit",
        "execute",
    }
)

L2_NORM_ATOL: float = 1e-4

IdArray = NDArray[np.int64]
FloatMatrix = NDArray[np.float32]


class SearchParams(TypedDict, total=False):
    """Optional engine search knobs; echoed in ``SearchResult.effective_params``."""

    nprobe: int
    ef_search: int
    refine_factor: float
    exact: bool


@runtime_checkable
class IndexAdapter(Protocol):
    """A read-only window onto a vector index.

    Every method is a pure read. No method may create, update, remove,
    lock, compact, rebuild, or otherwise mutate the target in any way.
    """

    @property
    def descriptor(self) -> TargetDescriptor:
        """Engine name, version, index kind, redacted target location."""
        ...

    @property
    def capabilities(self) -> Capabilities:
        """Which optional reads this engine supports. Drives UNAVAILABLE states."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimensionality of the target index."""
        ...

    @property
    def metric_space(self) -> MetricSpace:
        """COSINE | L2 | DOT — read from the index, never assumed."""
        ...

    def counts(self) -> IndexCounts:
        """Live / deleted / total / indexed counts, as far as the engine knows."""
        ...

    def iter_live_vectors(self, *, batch_size: int) -> Iterator[VectorBatch]:
        """Stream live vectors with stable IDs (order may vary across calls)."""
        ...

    def sample_ids(self, n: int, *, seed: int) -> IdArray:
        """Deterministic live-ID sample: same (n, seed, state) → same IDs."""
        ...

    def fetch_vectors(self, ids: IdArray) -> VectorBatch:
        """Random access by ID, for sampled subsets."""
        ...

    def search(
        self,
        queries: FloatMatrix,
        k: int,
        *,
        params: SearchParams,
    ) -> SearchResult:
        """The engine's own approximate search. This is the thing under test."""
        ...

    def partitions(self) -> PartitionStats | None:
        """IVF cell row counts. None if not an IVF index or not introspectable."""
        ...

    def graph_stats(self) -> GraphStats | None:
        """HNSW in-degree histogram and entry points. None if unavailable."""
        ...

    def close(self) -> None:
        """Release adapter resources without mutating the target index."""
        ...


def l2_normalize(
    vectors: FloatMatrix,
    *,
    atol: float = L2_NORM_ATOL,
) -> FloatMatrix:
    """Row-wise L2-normalise ``float32`` vectors and assert unit norms.

    Raises:
        ValueError: on zero-norm rows or norms outside ``atol`` of 1 after scaling.
    """
    if not isinstance(vectors, np.ndarray) or vectors.dtype != np.float32:
        msg = "vectors must be float32"
        raise ValueError(msg)
    if vectors.ndim != 2:
        msg = "vectors must be rank-2"
        raise ValueError(msg)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        msg = "zero-norm vector cannot be L2-normalised"
        raise ValueError(msg)
    out = np.ascontiguousarray(vectors / norms, dtype=np.float32)
    check = np.linalg.norm(out, axis=1)
    if np.any(np.abs(check - 1.0) >= atol):
        msg = f"post-normalisation norms must be within {atol} of 1"
        raise ValueError(msg)
    return out


class StringIdMapper:
    """Dense int64 IDs for opaque string keys (adapter-local; never export the map)."""

    def __init__(self) -> None:
        self._to_int: dict[str, int] = {}
        self._to_str: list[str] = []

    def encode(self, ids: Sequence[str]) -> IdArray:
        """Map string IDs to dense int64, assigning new indices in first-seen order."""
        out = np.empty(len(ids), dtype=np.int64)
        for i, key in enumerate(ids):
            existing = self._to_int.get(key)
            if existing is None:
                existing = len(self._to_str)
                self._to_int[key] = existing
                self._to_str.append(key)
            out[i] = existing
        return out

    def decode(self, ids: IdArray) -> list[str]:
        """Inverse of ``encode`` for adapter-internal use only."""
        return [self._to_str[int(i)] for i in ids]


def iter_vector_batches(
    ids: IdArray,
    vectors: FloatMatrix,
    *,
    batch_size: int,
) -> Iterator[VectorBatch]:
    """Yield ``VectorBatch`` slices over aligned ``ids`` / ``vectors``."""
    if batch_size < 1:
        msg = "batch_size must be >= 1"
        raise ValueError(msg)
    if ids.shape[0] != vectors.shape[0]:
        msg = "ids/vectors length mismatch"
        raise ValueError(msg)
    n = int(ids.shape[0])
    start = 0
    while start < n:
        end = min(start + batch_size, n)
        yield VectorBatch(
            ids=np.ascontiguousarray(ids[start:end], dtype=np.int64),
            vectors=np.ascontiguousarray(vectors[start:end], dtype=np.float32),
        )
        start = end
