"""Corpus and search result types shared across adapters and core.

Validation only — no I/O and no metric computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class IndexCounts:
    """Live / deleted / indexed cardinalities as far as the engine knows."""

    live: int
    deleted: int
    total: int
    indexed: int
    degenerate: int
    exact: bool
    read_at: datetime


@dataclass(frozen=True)
class VectorBatch:
    """A batch of live vectors with stable int64 IDs.

    ``vectors`` must be C-contiguous ``float32`` of shape ``(n, d)`` with
    ``n == len(ids)``.
    """

    ids: NDArray[np.int64]
    vectors: NDArray[np.float32]

    def __post_init__(self) -> None:
        """Reject bad dtype, layout, rank, or ids/vectors length mismatch."""
        ids = self.ids
        vectors = self.vectors
        if not isinstance(ids, np.ndarray) or ids.dtype != np.int64:
            msg = "ids must be an NDArray[int64]"
            raise ValueError(msg)
        if ids.ndim != 1:
            msg = "ids must be rank-1"
            raise ValueError(msg)
        if not isinstance(vectors, np.ndarray) or vectors.dtype != np.float32:
            msg = "vectors must be float32"
            raise ValueError(msg)
        if vectors.ndim != 2:
            msg = "vectors must be rank-2 with shape (n, d)"
            raise ValueError(msg)
        if not vectors.flags["C_CONTIGUOUS"]:
            msg = "vectors must be C-contiguous"
            raise ValueError(msg)
        if ids.shape[0] != vectors.shape[0]:
            msg = "ids/vectors length mismatch"
            raise ValueError(msg)


@dataclass(frozen=True)
class SearchResult:
    """Engine approximate search output.

    ``ids`` is shape ``(q, k)`` with ``-1`` padding for short returns.
    """

    ids: NDArray[np.int64]
    distances: NDArray[np.float32] | None
    effective_params: dict[str, object]


@dataclass(frozen=True)
class PartitionStats:
    """IVF (or similar) cell sizes."""

    sizes: NDArray[np.int64]
    includes_deleted: bool
    n_partitions: int


@dataclass(frozen=True)
class GraphStats:
    """HNSW-oriented graph introspection."""

    in_degree_histogram: NDArray[np.int64]
    entry_point_ids: NDArray[np.int64]
    entrypoint_tombstoned: bool | None
