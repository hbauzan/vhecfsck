"""Injectable corpus pathologies with analytically known true values.

Each operator is a pure function: inputs are never mutated. Annotations record
the induced ground truth for oracle tests in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.random import Generator, default_rng
from numpy.typing import NDArray

from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import GeneratedCorpus


@dataclass(frozen=True)
class GroundTruthAnnotation:
    """Known-true values induced by pathology operators."""

    dfi: float | None = None
    n_deleted: int = 0
    deleted_ids: tuple[int, ...] = ()
    deleted_per_fragment: tuple[int, ...] | None = None
    hub_ids: tuple[int, ...] = ()
    hub_share_lower_bound: float | None = None
    antihub_ids: tuple[int, ...] = ()
    antihub_fraction_lower_bound: float | None = None
    partition_sizes: tuple[int, ...] | None = None
    partition_cv: float | None = None


@dataclass(frozen=True)
class CorpusState:
    """Mutable-looking corpus snapshot that operators rewrite by replacement."""

    ids: NDArray[np.int64]
    vectors: NDArray[np.float32]
    cluster_ids: NDArray[np.int64]
    deleted: NDArray[np.bool_]
    partition_ids: NDArray[np.int64]
    metric_space: MetricSpace
    annotation: GroundTruthAnnotation


def corpus_state_from_generated(corpus: GeneratedCorpus) -> CorpusState:
    """Wrap a generated corpus as an all-live pathology state."""
    n = int(corpus.ids.shape[0])
    return CorpusState(
        ids=np.array(corpus.ids, dtype=np.int64, copy=True),
        vectors=np.array(corpus.vectors, dtype=np.float32, copy=True),
        cluster_ids=np.array(corpus.cluster_ids, dtype=np.int64, copy=True),
        deleted=np.zeros(n, dtype=np.bool_),
        partition_ids=np.array(corpus.cluster_ids, dtype=np.int64, copy=True),
        metric_space=corpus.spec.metric_space,
        annotation=GroundTruthAnnotation(),
    )


def _partition_cv(sizes: list[int]) -> float:
    if not sizes:
        return 0.0
    mean = sum(sizes) / len(sizes)
    if mean == 0.0:
        return 0.0
    var = sum((s - mean) ** 2 for s in sizes) / len(sizes)
    return float((var**0.5) / mean)


def _cluster_centroids(
    vectors: NDArray[np.float32],
    cluster_ids: NDArray[np.int64],
    deleted: NDArray[np.bool_],
) -> NDArray[np.float32]:
    n_clusters = int(cluster_ids.max()) + 1 if cluster_ids.size else 0
    d = int(vectors.shape[1])
    centroids = np.zeros((n_clusters, d), dtype=np.float32)
    counts = np.zeros(n_clusters, dtype=np.int64)
    for i in range(vectors.shape[0]):
        if deleted[i]:
            continue
        c = int(cluster_ids[i])
        centroids[c] += vectors[i]
        counts[c] += np.int64(1)
    for c in range(n_clusters):
        if counts[c] > 0:
            centroids[c] /= np.float32(counts[c])
    return centroids


def apply_churn(
    state: CorpusState,
    *,
    delete_fraction: float,
    skew: float,
    seed: int,
) -> CorpusState:
    """Mark tombstones; DFI = dead / (live + dead) by construction."""
    if not 0.0 <= delete_fraction <= 1.0:
        msg = "delete_fraction must be in [0, 1]"
        raise ValueError(msg)
    n = int(state.ids.shape[0])
    live_idx = [i for i in range(n) if not bool(state.deleted[i])]
    n_live = len(live_idx)
    n_delete = round(delete_fraction * n_live)
    n_delete = min(n_delete, n_live)

    rng = default_rng(seed)
    deleted = np.array(state.deleted, dtype=np.bool_, copy=True)

    if n_delete == 0:
        dfi = 0.0
        deleted_ids: tuple[int, ...] = ()
        per_frag = tuple(0 for _ in range(int(state.cluster_ids.max()) + 1 if n else 0))
        return CorpusState(
            ids=np.array(state.ids, copy=True),
            vectors=np.array(state.vectors, copy=True),
            cluster_ids=np.array(state.cluster_ids, copy=True),
            deleted=deleted,
            partition_ids=np.array(state.partition_ids, copy=True),
            metric_space=state.metric_space,
            annotation=replace(
                state.annotation,
                dfi=dfi,
                n_deleted=int(np.sum(deleted)),
                deleted_ids=deleted_ids,
                deleted_per_fragment=per_frag,
            ),
        )

    if skew == 0.0:
        chosen = rng.choice(
            np.asarray(live_idx, dtype=np.int64),
            size=n_delete,
            replace=False,
        )
        for i in chosen:
            deleted[int(i)] = True
    else:
        # Concentrate deletions into a few clusters (power-law over cluster ranks).
        n_clusters = int(state.cluster_ids.max()) + 1
        ranks = np.arange(1, n_clusters + 1, dtype=np.float32)
        weights = ranks ** np.float32(-skew)
        weights = weights / weights.sum()
        # Assign quota per cluster, then sample within live members.
        raw = weights * np.float32(n_delete)
        quotas = np.floor(raw).astype(np.int64)
        quotas = np.maximum(quotas, 0)
        # Fix sum to n_delete.
        delta = n_delete - int(quotas.sum())
        order = np.argsort(-quotas, kind="mergesort")
        k = 0
        while delta > 0:
            quotas[int(order[k % n_clusters])] += np.int64(1)
            delta -= 1
            k += 1
        for c in range(n_clusters):
            members = [i for i in live_idx if int(state.cluster_ids[i]) == c]
            take = min(int(quotas[c]), len(members))
            if take == 0:
                continue
            pick = rng.choice(
                np.asarray(members, dtype=np.int64),
                size=take,
                replace=False,
            )
            for i in pick:
                deleted[int(i)] = True
        # If quotas undershot (empty clusters), fill remaining uniformly.
        still = n_delete - int(np.sum(deleted) - int(np.sum(state.deleted)))
        if still > 0:
            remain = [i for i in live_idx if not bool(deleted[i])]
            pick = rng.choice(
                np.asarray(remain, dtype=np.int64),
                size=min(still, len(remain)),
                replace=False,
            )
            for i in pick:
                deleted[int(i)] = True

    dead = int(np.sum(deleted))
    live = n - dead
    dfi = dead / (live + dead) if (live + dead) else 0.0
    # Prefer the requested fraction when round-trip is exact.
    if abs(dfi - delete_fraction) < 1e-12:
        dfi = float(delete_fraction)

    deleted_ids = tuple(sorted(int(state.ids[i]) for i in range(n) if bool(deleted[i])))
    n_clusters = int(state.cluster_ids.max()) + 1 if n else 0
    per_frag_list = [0] * n_clusters
    for i in range(n):
        if deleted[i]:
            per_frag_list[int(state.cluster_ids[i])] += 1

    return CorpusState(
        ids=np.array(state.ids, copy=True),
        vectors=np.array(state.vectors, copy=True),
        cluster_ids=np.array(state.cluster_ids, copy=True),
        deleted=deleted,
        partition_ids=np.array(state.partition_ids, copy=True),
        metric_space=state.metric_space,
        annotation=replace(
            state.annotation,
            dfi=dfi,
            n_deleted=dead,
            deleted_ids=deleted_ids,
            deleted_per_fragment=tuple(per_frag_list),
        ),
    )


def inject_hubs(
    state: CorpusState,
    *,
    n_hubs: int,
    strength: float,
    seed: int,
) -> CorpusState:
    """Append cannibalising hubs near inter-cluster / dense-core centroids."""
    if n_hubs < 1:
        msg = "n_hubs must be >= 1"
        raise ValueError(msg)
    if strength <= 0:
        msg = "strength must be > 0"
        raise ValueError(msg)

    rng = default_rng(seed)
    centroids = _cluster_centroids(state.vectors, state.cluster_ids, state.deleted)
    n_clusters = int(centroids.shape[0])
    d = int(state.vectors.shape[1])
    live = [i for i in range(state.ids.shape[0]) if not bool(state.deleted[i])]
    hubs = np.empty((n_hubs, d), dtype=np.float32)
    hub_clusters = np.empty(n_hubs, dtype=np.int64)

    # Cluster sizes for assigning hub "home" labels.
    sizes = [0] * max(n_clusters, 1)
    for i in live:
        sizes[int(state.cluster_ids[i])] += 1
    ranked = sorted(range(len(sizes)), key=lambda c: (-sizes[c], c))

    for h in range(n_hubs):
        c = ranked[h % len(ranked)] if ranked else 0
        hub_clusters[h] = np.int64(c)
        members = [i for i in live if int(state.cluster_ids[i]) == c]
        if members:
            vec = np.zeros(d, dtype=np.float32)
            for idx in members:
                vec += state.vectors[idx]
            vec /= np.float32(len(members))
            # Optional light blend toward a second cluster centre (inter-cluster).
            if n_clusters >= 2 and strength > 0:
                c2 = ranked[(h + 1) % len(ranked)]
                # Cap blend so the hub stays inside its home cluster's mass.
                w = np.float32(min(0.15, 0.03 * strength))
                vec = (np.float32(1) - w) * vec + w * centroids[c2]
        elif n_clusters > 0:
            vec = np.array(centroids[c], dtype=np.float32, copy=True)
        else:
            vec = rng.standard_normal(d, dtype=np.float32)

        # Tiny deterministic jitter so hubs are not identical when co-located.
        jitter = rng.standard_normal(d, dtype=np.float32) * np.float32(1e-4)
        vec = vec + jitter

        if state.metric_space is MetricSpace.COSINE:
            norm = np.sqrt(np.sum(vec * vec, dtype=np.float32))
            if norm > 0:
                vec = vec / norm
        elif state.metric_space is MetricSpace.DOT:
            norm = np.sqrt(np.sum(vec * vec, dtype=np.float32))
            if norm > 0:
                vec = vec / norm
            vec = vec * np.float32(1.0 + strength)
        hubs[h] = vec

    next_id = int(state.ids.max()) + 1 if state.ids.size else 0
    new_ids = np.arange(next_id, next_id + n_hubs, dtype=np.int64)
    ids = np.concatenate([state.ids, new_ids])
    vectors = np.concatenate([state.vectors, hubs], axis=0)
    cluster_ids = np.concatenate([state.cluster_ids, hub_clusters])
    deleted = np.concatenate(
        [state.deleted, np.zeros(n_hubs, dtype=np.bool_)],
    )
    partition_ids = np.concatenate([state.partition_ids, hub_clusters])

    n_total = int(ids.shape[0])
    hub_share_lower_bound = min(1.0, (n_hubs * min(strength, 5.0)) / max(n_total, 1))

    return CorpusState(
        ids=ids,
        vectors=np.ascontiguousarray(vectors, dtype=np.float32),
        cluster_ids=cluster_ids,
        deleted=deleted,
        partition_ids=partition_ids,
        metric_space=state.metric_space,
        annotation=replace(
            state.annotation,
            hub_ids=tuple(int(x) for x in new_ids),
            hub_share_lower_bound=float(hub_share_lower_bound),
        ),
    )


def inject_antihubs(
    state: CorpusState,
    *,
    n_antihubs: int,
    distance_factor: float,
    seed: int,
) -> CorpusState:
    """Append isolated outliers far from live mass."""
    if n_antihubs < 1:
        msg = "n_antihubs must be >= 1"
        raise ValueError(msg)
    if distance_factor <= 0:
        msg = "distance_factor must be > 0"
        raise ValueError(msg)

    rng = default_rng(seed)
    live = [i for i in range(state.ids.shape[0]) if not bool(state.deleted[i])]
    d = int(state.vectors.shape[1])
    if live:
        center = np.zeros(d, dtype=np.float32)
        for i in live:
            center += state.vectors[i]
        center /= np.float32(len(live))
        # Typical radius.
        acc = np.float32(0)
        for i in live:
            delta = state.vectors[i] - center
            acc += np.sum(delta * delta, dtype=np.float32)
        radius = np.sqrt(acc / np.float32(len(live))) + np.float32(1e-6)
    else:
        center = np.zeros(d, dtype=np.float32)
        radius = np.float32(1)

    anti = np.empty((n_antihubs, d), dtype=np.float32)
    anti_clusters = np.zeros(n_antihubs, dtype=np.int64)
    for a in range(n_antihubs):
        direction = rng.standard_normal(d, dtype=np.float32)
        nrm = np.sqrt(np.sum(direction * direction, dtype=np.float32))
        if nrm > 0:
            direction = direction / nrm
        anti[a] = center + direction * (radius * np.float32(distance_factor))
        if state.metric_space is MetricSpace.COSINE:
            nrm2 = np.sqrt(np.sum(anti[a] * anti[a], dtype=np.float32))
            if nrm2 > 0:
                anti[a] = anti[a] / nrm2

    next_id = int(state.ids.max()) + 1 if state.ids.size else 0
    new_ids = np.arange(next_id, next_id + n_antihubs, dtype=np.int64)
    n_total = int(state.ids.shape[0]) + n_antihubs
    frac = n_antihubs / n_total

    return CorpusState(
        ids=np.concatenate([state.ids, new_ids]),
        vectors=np.ascontiguousarray(
            np.concatenate([state.vectors, anti], axis=0),
            dtype=np.float32,
        ),
        cluster_ids=np.concatenate([state.cluster_ids, anti_clusters]),
        deleted=np.concatenate([state.deleted, np.zeros(n_antihubs, dtype=np.bool_)]),
        partition_ids=np.concatenate([state.partition_ids, anti_clusters]),
        metric_space=state.metric_space,
        annotation=replace(
            state.annotation,
            antihub_ids=tuple(int(x) for x in new_ids),
            antihub_fraction_lower_bound=float(frac),
        ),
    )


def _append_to_partition(
    state: CorpusState,
    *,
    partition: int,
    count: int,
    rng: Generator,
) -> CorpusState:
    """Append ``count`` vectors into an existing partition (no centroid retrain)."""
    if count <= 0:
        return state
    members = [
        i
        for i in range(state.ids.shape[0])
        if int(state.partition_ids[i]) == partition and not bool(state.deleted[i])
    ]
    d = int(state.vectors.shape[1])
    proto = state.vectors[int(members[0])] if members else np.zeros(d, dtype=np.float32)
    block = np.empty((count, d), dtype=np.float32)
    for j in range(count):
        noise = rng.standard_normal(d, dtype=np.float32) * np.float32(0.01)
        block[j] = proto + noise
    next_id = int(state.ids.max()) + 1 if state.ids.size else 0
    new_ids = np.arange(next_id, next_id + count, dtype=np.int64)
    part = np.full(count, np.int64(partition), dtype=np.int64)
    cl = np.full(count, np.int64(partition), dtype=np.int64)
    return CorpusState(
        ids=np.concatenate([state.ids, new_ids]),
        vectors=np.ascontiguousarray(
            np.concatenate([state.vectors, block], axis=0),
            dtype=np.float32,
        ),
        cluster_ids=np.concatenate([state.cluster_ids, cl]),
        deleted=np.concatenate([state.deleted, np.zeros(count, dtype=np.bool_)]),
        partition_ids=np.concatenate([state.partition_ids, part]),
        metric_space=state.metric_space,
        annotation=state.annotation,
    )


def skew_partitions(
    state: CorpusState,
    *,
    seed: int,
    target_cv: float | None = None,
    growth_factor: float | None = None,
) -> CorpusState:
    """Grow a subset of IVF cells without retraining (lance#4164 mechanism)."""
    if target_cv is None and growth_factor is None:
        msg = "provide target_cv or growth_factor"
        raise ValueError(msg)
    if target_cv is not None and growth_factor is not None:
        msg = "provide only one of target_cv or growth_factor"
        raise ValueError(msg)

    rng = default_rng(seed)
    n_parts = int(state.partition_ids.max()) + 1 if state.partition_ids.size else 0
    if n_parts == 0:
        return state

    current = state
    sizes = [
        int(
            sum(
                1
                for i in range(current.ids.shape[0])
                if int(current.partition_ids[i]) == p and not bool(current.deleted[i])
            )
        )
        for p in range(n_parts)
    ]

    if growth_factor is not None:
        if growth_factor < 1.0:
            msg = "growth_factor must be >= 1"
            raise ValueError(msg)
        # Grow the largest half of partitions.
        order = sorted(range(n_parts), key=lambda p: (-sizes[p], p))
        grow_set = order[: max(1, n_parts // 2)]
        for p in grow_set:
            add = round(sizes[p] * (growth_factor - 1.0))
            current = _append_to_partition(
                current,
                partition=p,
                count=add,
                rng=rng,
            )
            sizes[p] += add
    else:
        assert target_cv is not None
        if target_cv < 0:
            msg = "target_cv must be >= 0"
            raise ValueError(msg)
        # Greedily append to the current largest partition until CV reaches target.
        guard = 0
        max_steps = max(10_000, 5 * int(current.ids.shape[0]))
        while _partition_cv(sizes) < target_cv * 0.95 and guard < max_steps:
            # Largest partition (tie-break: lowest id).
            best = 0
            for p in range(1, n_parts):
                if sizes[p] > sizes[best] or (sizes[p] == sizes[best] and p < best):
                    best = p
            current = _append_to_partition(current, partition=best, count=1, rng=rng)
            sizes[best] += 1
            guard += 1

    cv = _partition_cv(sizes)
    return CorpusState(
        ids=current.ids,
        vectors=current.vectors,
        cluster_ids=current.cluster_ids,
        deleted=current.deleted,
        partition_ids=current.partition_ids,
        metric_space=current.metric_space,
        annotation=replace(
            current.annotation,
            partition_sizes=tuple(sizes),
            partition_cv=float(cv),
        ),
    )
