"""Loop-based reference for the synthetic IVF k-means build.

This is the implementation that `vhecfsck/adapters/synthetic_adapter.py` shipped
before the build was vectorised: a per-row Python loop over per-centroid scalar
distances. It is transcribed here verbatim, self-contained (its own distance
helpers, its own bucket construction), so it stays an independent check rather
than a rename of the production path.

Never optimise this module (``roadmap/lessons-learned.md`` §27). If a test is too
slow, shrink the input. Production code under ``vhecfsck/`` must never import it
(enforced by import-linter).
"""

from __future__ import annotations

import numpy as np
from numpy.random import default_rng
from numpy.typing import NDArray
from vhecfsck.models import MetricSpace

# Mirrors ``synthetic_adapter._KMEANS_ITERS``. The differential test asserts the
# two are equal, so a change on the production side cannot silently make the
# oracle compare a different number of iterations.
KMEANS_ITERS = 12


def naive_distance(
    a: NDArray[np.float32],
    b: NDArray[np.float32],
    metric: MetricSpace,
) -> np.float32:
    """Lower-is-better float32 distance between two vectors."""
    if metric is MetricSpace.L2:
        delta = a - b
        return np.float32(np.sqrt(np.sum(delta * delta, dtype=np.float32)))
    if metric is MetricSpace.COSINE:
        return np.float32(1.0) - np.float32(np.sum(a * b, dtype=np.float32))
    return np.float32(-np.sum(a * b, dtype=np.float32))


def naive_pairwise_distances(
    matrix: NDArray[np.float32],
    query: NDArray[np.float32],
    metric: MetricSpace,
) -> NDArray[np.float32]:
    """Distance from each row of ``matrix`` to ``query``, one scalar call per row."""
    n = int(matrix.shape[0])
    out = np.empty(n, dtype=np.float32)
    for i in range(n):
        out[i] = naive_distance(matrix[i], query, metric)
    return out


def naive_lists_from_assignment(
    assignment: NDArray[np.int64],
    n_lists: int,
) -> list[NDArray[np.int64]]:
    """Bucket row indices by assigned cell, ascending within each bucket."""
    buckets: list[list[int]] = [[] for _ in range(n_lists)]
    for i in range(assignment.shape[0]):
        c = int(assignment[i])
        if 0 <= c < n_lists:
            buckets[c].append(i)
    return [np.asarray(b, dtype=np.int64) for b in buckets]


def naive_fit_ivf(
    vectors: NDArray[np.float32],
    *,
    n_lists: int,
    seed: int,
    metric: MetricSpace,
) -> tuple[NDArray[np.float32], NDArray[np.int64], list[NDArray[np.int64]]]:
    """Lloyd's k-means over ``KMEANS_ITERS`` sweeps, one Python loop per row.

    Seeded by ``default_rng(seed).choice`` without replacement. When ``n <
    n_lists`` the unused centroids are padded with copies of the last one, which
    the ascending tie-break leaves permanently empty.
    """
    n = int(vectors.shape[0])
    d = int(vectors.shape[1])
    if n == 0:
        return (
            np.empty((n_lists, d), dtype=np.float32),
            np.empty(0, dtype=np.int64),
            [np.empty(0, dtype=np.int64) for _ in range(n_lists)],
        )
    rng = default_rng(seed)
    n_lists_i = min(n_lists, n)
    init_idx = rng.choice(n, size=n_lists_i, replace=False)
    centroids = np.array(vectors[init_idx], dtype=np.float32, copy=True)
    if n_lists_i < n_lists:
        pad = np.repeat(centroids[-1:], n_lists - n_lists_i, axis=0)
        centroids = np.concatenate([centroids, pad], axis=0)

    assignment = np.zeros(n, dtype=np.int64)
    for _ in range(KMEANS_ITERS):
        for i in range(n):
            dists = naive_pairwise_distances(centroids, vectors[i], metric)
            best = 0
            best_d = float(dists[0])
            for c in range(1, n_lists):
                dc = float(dists[c])
                if dc < best_d or (dc == best_d and c < best):
                    best = c
                    best_d = dc
            assignment[i] = np.int64(best)
        counts = np.zeros(n_lists, dtype=np.int64)
        new_c = np.zeros((n_lists, d), dtype=np.float32)
        for i in range(n):
            c = int(assignment[i])
            new_c[c] += vectors[i]
            counts[c] += np.int64(1)
        for c in range(n_lists):
            if counts[c] > 0:
                centroids[c] = new_c[c] / np.float32(counts[c])
                if metric is MetricSpace.COSINE:
                    nrm = float(np.sqrt(np.sum(centroids[c] * centroids[c])))
                    if nrm > 0:
                        centroids[c] = centroids[c] / np.float32(nrm)

    lists = naive_lists_from_assignment(assignment, n_lists)
    return np.ascontiguousarray(centroids, dtype=np.float32), assignment, lists
