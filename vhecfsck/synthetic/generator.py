"""Synthetic corpus construction (clusters, dims, seeds).

Generates reproducible float32 corpora for adapter and metric tests.
Imports only models and numpy — never core or adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.random import Generator, default_rng
from numpy.typing import NDArray

from vhecfsck.models import MetricSpace

_DEFAULT_BLOCK: int = 8192
_NORM_ATOL: float = 1e-4


@dataclass(frozen=True)
class CorpusSpec:
    """Exact parameters used to build a synthetic corpus."""

    n: int
    d: int
    n_clusters: int
    cluster_std: float
    cluster_size_skew: float
    seed: int
    metric_space: MetricSpace
    cluster_sizes: tuple[int, ...]
    norm_mean: float
    norm_std: float
    block_size: int


@dataclass(frozen=True)
class GeneratedCorpus:
    """Seeded corpus arrays plus the spec that produced them."""

    ids: NDArray[np.int64]
    vectors: NDArray[np.float32]
    cluster_ids: NDArray[np.int64]
    spec: CorpusSpec


def _cluster_sizes(n: int, n_clusters: int, skew: float) -> NDArray[np.int64]:
    """Allocate per-cluster cardinalities (uniform or power-law skew)."""
    if n < n_clusters:
        msg = f"n ({n}) must be >= n_clusters ({n_clusters})"
        raise ValueError(msg)
    if skew == 0.0:
        base = n // n_clusters
        sizes = np.full(n_clusters, base, dtype=np.int64)
        sizes[: n % n_clusters] += np.int64(1)
        return sizes
    ranks = np.arange(1, n_clusters + 1, dtype=np.float32)
    weights = ranks ** np.float32(-skew)
    weights = weights / weights.sum()
    raw = weights * np.float32(n)
    sizes = np.floor(raw).astype(np.int64, copy=False)
    sizes = np.maximum(sizes, np.int64(1))
    # Fix sum by adjusting the largest bucket (deterministic).
    delta = int(n) - int(sizes.sum())
    order = np.argsort(-sizes, kind="mergesort")
    i = 0
    while delta != 0:
        idx = int(order[i % n_clusters])
        if delta > 0:
            sizes[idx] += np.int64(1)
            delta -= 1
        elif sizes[idx] > 1:
            sizes[idx] -= np.int64(1)
            delta += 1
        i += 1
        if i > n * 2:
            msg = "failed to reconcile cluster sizes to n"
            raise RuntimeError(msg)
    return np.asarray(sizes, dtype=np.int64)


def _l2_normalize_inplace(block: NDArray[np.float32]) -> None:
    """Scale rows to unit L2 norm using float32 arithmetic only."""
    sq_arr = np.sum(block * block, axis=1, keepdims=True, dtype=np.float32)
    sq: NDArray[np.float32] = np.asarray(sq_arr, dtype=np.float32)
    if np.any(sq[:, 0] == np.float32(0)):
        msg = "zero-norm vector in synthetic corpus"
        raise ValueError(msg)
    inv = np.empty_like(sq)
    np.sqrt(sq, out=inv)
    np.divide(np.float32(1), inv, out=inv)
    block *= inv
    norms = np.sqrt(np.sum(block * block, axis=1, dtype=np.float32))
    if np.any(np.abs(norms - np.float32(1)) >= np.float32(_NORM_ATOL)):
        msg = "cosine normalisation failed atol check"
        raise ValueError(msg)


def _apply_dot_norms(
    block: NDArray[np.float32],
    rng: np.random.Generator,
    *,
    norm_mean: float,
    norm_std: float,
) -> None:
    """Unit-normalise then scale rows to a float32 norm distribution."""
    _l2_normalize_inplace(block)
    take = block.shape[0]
    scales: NDArray[np.float32]
    if norm_std == 0.0:
        scales = np.full(take, np.float32(norm_mean), dtype=np.float32)
    else:
        scales = np.asarray(
            rng.standard_normal(take, dtype=np.float32),
            dtype=np.float32,
        )
        scales *= np.float32(norm_std)
        scales += np.float32(norm_mean)
        np.abs(scales, out=scales)
        scales = np.maximum(scales, np.float32(1e-6))
    block *= scales[:, np.newaxis]


def generate_corpus(
    n: int,
    d: int,
    *,
    n_clusters: int,
    cluster_std: float,
    cluster_size_skew: float,
    seed: int,
    metric_space: MetricSpace,
    norm_mean: float = 1.0,
    norm_std: float = 0.0,
    block_size: int = _DEFAULT_BLOCK,
) -> GeneratedCorpus:
    """Build a seeded clustered corpus as C-contiguous float32 vectors.

    Generation writes into a preallocated output array in blocks so only one
    scratch block is live beyond the output.
    """
    if n < 1 or d < 1 or n_clusters < 1:
        msg = "n, d, and n_clusters must be positive"
        raise ValueError(msg)
    if block_size < 1:
        msg = "block_size must be >= 1"
        raise ValueError(msg)
    if cluster_std < 0:
        msg = "cluster_std must be >= 0"
        raise ValueError(msg)

    sizes = _cluster_sizes(n, n_clusters, cluster_size_skew)
    rng: Generator = default_rng(seed)
    centroids = rng.standard_normal((n_clusters, d), dtype=np.float32)
    std = np.float32(cluster_std)

    ids = np.arange(n, dtype=np.int64)
    vectors = np.empty((n, d), dtype=np.float32)
    cluster_ids = np.empty(n, dtype=np.int64)

    offset = 0
    for c_idx, size in enumerate(sizes):
        size_i = int(size)
        cluster_ids[offset : offset + size_i] = np.int64(c_idx)
        remaining = size_i
        pos = offset
        while remaining > 0:
            take = min(block_size, remaining)
            scratch = rng.standard_normal((take, d), dtype=np.float32)
            scratch *= std
            scratch += centroids[c_idx]
            if metric_space is MetricSpace.COSINE:
                _l2_normalize_inplace(scratch)
            elif metric_space is MetricSpace.DOT:
                _apply_dot_norms(
                    scratch,
                    rng,
                    norm_mean=norm_mean,
                    norm_std=norm_std,
                )
            vectors[pos : pos + take] = scratch
            pos += take
            remaining -= take
        offset += size_i

    spec = CorpusSpec(
        n=n,
        d=d,
        n_clusters=n_clusters,
        cluster_std=cluster_std,
        cluster_size_skew=cluster_size_skew,
        seed=seed,
        metric_space=metric_space,
        cluster_sizes=tuple(int(s) for s in sizes),
        norm_mean=norm_mean,
        norm_std=norm_std,
        block_size=block_size,
    )
    return GeneratedCorpus(
        ids=ids,
        vectors=vectors,
        cluster_ids=cluster_ids,
        spec=spec,
    )
