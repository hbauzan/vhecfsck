"""Naive reference implementations for differential testing (P2-03).

These functions are deliberately slow and written for readability. They are the
independent check against which optimised ``core/`` paths are compared. Never
optimise this module: if a test is too slow, shrink the input.

Production code under ``vhecfsck/`` must never import this package
(``roadmap/01-architecture.md`` §4; enforced by import-linter).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from vhecfsck.models import MetricSpace


def _pairwise_score(
    a: Sequence[float],
    b: Sequence[float],
    metric_space: MetricSpace,
) -> float:
    """Lower-is-better score in every metric space.

    * ``L2`` — Euclidean distance (sqrt applied; ordering matches squared L2).
    * ``COSINE`` — ``1 - cos``; callers supply already-normalised vectors
      (``02-metrics-spec.md`` §1.1).
    * ``DOT`` — ``-dot`` so larger inner products rank first.
    """
    dim = len(a)
    if metric_space is MetricSpace.L2:
        acc = 0.0
        for i in range(dim):
            d = float(a[i]) - float(b[i])
            acc += d * d
        return math.sqrt(acc)
    if metric_space is MetricSpace.COSINE:
        dot = 0.0
        for i in range(dim):
            dot += float(a[i]) * float(b[i])
        return 1.0 - dot
    # DOT — higher similarity is better → negate for ascending sort.
    dot = 0.0
    for i in range(dim):
        dot += float(a[i]) * float(b[i])
    return -dot


def naive_knn(
    corpus: NDArray[np.floating],
    queries: NDArray[np.floating],
    k: int,
    metric_space: MetricSpace,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Exact k-NN by full pairwise scores + sort.

    Implements the brute-force half of canary ground truth
    (``02-metrics-spec.md`` §2.2-§2.3, Fixture A in §2.6). For each query,
    score every corpus row, sort by ``(score ascending, id ascending)``, take
    the first ``k``. Ties break by ascending vector ID (§1.2).

    Returns
    -------
    ids :
        ``(n_queries, k)`` int64 neighbour ids (row index == id when ids are
        ``0..n-1``; here the id is the corpus row index).
    distances :
        ``(n_queries, k)`` float64 lower-is-better scores (Euclidean for L2).
    """
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)
    n = int(corpus.shape[0])
    n_q = int(queries.shape[0])
    take = min(k, n)
    out_ids = np.full((n_q, k), -1, dtype=np.int64)
    out_dist = np.full((n_q, k), np.inf, dtype=np.float64)
    for qi in range(n_q):
        q = queries[qi]
        scored: list[tuple[float, int]] = []
        for ci in range(n):
            score = _pairwise_score(corpus[ci], q, metric_space)
            scored.append((score, ci))
        # Explicit full sort — never argpartition. Readability over speed.
        scored.sort(key=lambda t: (t[0], t[1]))
        for j in range(take):
            out_ids[qi, j] = scored[j][1]
            out_dist[qi, j] = scored[j][0]
    return out_ids, out_dist


def naive_recall(
    gt_ids: Sequence[int],
    returned_ids: Sequence[int],
    *,
    returned_true_distances: Sequence[float],
    d_k: float,
    n_eff: int | None = None,
    rtol: float = 1e-6,
) -> tuple[float, float]:
    """Per-query recall_id and tie-tolerant recall_dist.

    Implements ``02-metrics-spec.md`` §2.2 and ADR-0007 (Fixture A in §2.6)::

        recall_id   = |GT_K ∩ R_K| / n_eff
        recall_dist = |{ i ∈ R_K : true_dist(q,i) ≤ d_K · (1 + rtol) }| / n_eff

    ``returned_true_distances`` must be recomputed from corpus vectors, never
    taken from the engine. Distances use the same lower-is-better convention
    as :func:`naive_knn` (so the ``≤`` form of the threshold applies to L2,
    COSINE-as-``1-cos``, and DOT-as-``-dot`` alike).
    """
    if len(returned_ids) != len(returned_true_distances):
        msg = "returned_ids and returned_true_distances must have the same length"
        raise ValueError(msg)
    eff = n_eff if n_eff is not None else len(gt_ids)
    if eff <= 0:
        msg = "n_eff must be > 0"
        raise ValueError(msg)

    gt_set = {int(x) for x in gt_ids}
    # Deduplicate returned ids for ID-set recall (spec §2.5 case 3); first wins.
    seen: set[int] = set()
    unique_returned: list[int] = []
    for rid in returned_ids:
        ir = int(rid)
        if ir in seen:
            continue
        seen.add(ir)
        unique_returned.append(ir)

    hits_id = 0
    for rid in unique_returned:
        if rid in gt_set:
            hits_id += 1
    recall_id = hits_id / float(eff)

    threshold = float(d_k) * (1.0 + float(rtol))
    hits_dist = 0
    seen_dist: set[int] = set()
    for rid, dist in zip(returned_ids, returned_true_distances, strict=True):
        ir = int(rid)
        if ir in seen_dist:
            continue
        seen_dist.add(ir)
        if float(dist) <= threshold:
            hits_dist += 1
    recall_dist = hits_dist / float(eff)
    return recall_id, recall_dist


def naive_nk(
    corpus: NDArray[np.floating],
    k: int,
    metric_space: MetricSpace,
) -> NDArray[np.int64]:
    """O(S²) neighbour-count histogram for hubness.

    Implements the definition in ``02-metrics-spec.md`` §3.1 (Fixture B in
    §3.7): for each point, find its exact ``k`` nearest neighbours within the
    sample excluding itself; ``N_k[i]`` is how often id ``i`` appears in those
    lists. Ties break by ascending id. Invariant: ``sum(N_k) == S * k``.
    """
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)
    n = int(corpus.shape[0])
    if k >= n:
        msg = "k must be < number of points (self is excluded)"
        raise ValueError(msg)
    counts = [0] * n
    for qi in range(n):
        scored: list[tuple[float, int]] = []
        for ci in range(n):
            if ci == qi:
                continue
            score = _pairwise_score(corpus[ci], corpus[qi], metric_space)
            scored.append((score, ci))
        scored.sort(key=lambda t: (t[0], t[1]))
        for j in range(k):
            neighbour = scored[j][1]
            counts[neighbour] += 1
    return np.asarray(counts, dtype=np.int64)


def naive_cv(sizes: Sequence[float]) -> float:
    """Partition-size coefficient of variation (population, ddof=0).

    Implements ``02-metrics-spec.md`` §5.1 (Fixture C in §5.4)::

        cv = population_std(sizes) / mean(sizes)

    Partitions are the whole population, not a sample — ``ddof`` is explicitly
    zero. Returns ``nan`` when ``mean == 0`` (caller maps that to UNAVAILABLE).
    """
    n = len(sizes)
    if n == 0:
        msg = "sizes must be non-empty"
        raise ValueError(msg)
    total = 0.0
    for s in sizes:
        total += float(s)
    mean = total / float(n)
    if mean == 0.0:
        return float("nan")
    acc = 0.0
    for s in sizes:
        d = float(s) - mean
        acc += d * d
    std = math.sqrt(acc / float(n))
    return std / mean
