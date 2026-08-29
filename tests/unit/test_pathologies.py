"""P1-04: injectable synthetic pathologies."""

from __future__ import annotations

import numpy as np
from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import (
    CorpusState,
    apply_churn,
    corpus_state_from_generated,
    inject_antihubs,
    inject_hubs,
    skew_partitions,
)


def _base_state(*, n: int = 500, d: int = 16, seed: int = 1) -> CorpusState:
    gen = generate_corpus(
        n,
        d,
        n_clusters=8,
        cluster_std=0.15,
        cluster_size_skew=0.5,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    return corpus_state_from_generated(gen)


def test_apply_churn_exact_tombstones_and_dfi() -> None:
    state = _base_state(n=1000)
    out = apply_churn(state, delete_fraction=0.2, skew=0.0, seed=7)
    n_deleted = int(np.sum(out.deleted))
    assert n_deleted == 200
    assert out.annotation.dfi == 0.2
    assert out.annotation.n_deleted == 200
    assert len(out.annotation.deleted_ids) == 200
    # Pure: input untouched.
    assert int(np.sum(state.deleted)) == 0
    assert state.vectors.tobytes() == _base_state(n=1000).vectors.tobytes()


def test_inject_hubs_are_frequent_top10_neighbours() -> None:
    # Tight, small clusters so a centroid hub competes inside top-10.
    gen = generate_corpus(
        240,
        8,
        n_clusters=24,
        cluster_std=0.05,
        cluster_size_skew=0.0,
        seed=3,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    out = inject_hubs(state, n_hubs=3, strength=4.0, seed=11)
    assert len(out.annotation.hub_ids) == 3
    assert out.annotation.hub_share_lower_bound is not None
    assert out.annotation.hub_share_lower_bound > 0.0

    hub_set = set(out.annotation.hub_ids)
    live_idx = [i for i in range(out.ids.shape[0]) if not bool(out.deleted[i])]
    hub_rows = [i for i in live_idx if int(out.ids[i]) in hub_set]
    hub_clusters = {int(out.cluster_ids[i]) for i in hub_rows}
    candidates = [
        i
        for i in live_idx
        if int(out.ids[i]) not in hub_set and int(out.cluster_ids[i]) in hub_clusters
    ]
    rng = np.random.default_rng(99)
    take = min(60, len(candidates))
    probe_idx = [
        int(candidates[j])
        for j in rng.choice(len(candidates), size=take, replace=False)
    ]

    hub_slots = 0
    total_slots = 0
    for pi in probe_idx:
        q = out.vectors[pi]
        dists = []
        for j in live_idx:
            if j == pi:
                continue
            delta = out.vectors[j] - q
            dist = float(np.sum(delta * delta, dtype=np.float32))
            dists.append((dist, int(out.ids[j])))
        dists.sort(key=lambda t: (t[0], t[1]))
        top10 = {did for _, did in dists[:10]}
        hub_slots += len(top10 & hub_set)
        total_slots += 10

    assert hub_slots / total_slots > 0.05


def test_skew_partitions_target_cv_within_5_percent() -> None:
    state = _base_state(n=800, seed=5)
    out = skew_partitions(state, target_cv=1.5, seed=2)
    sizes = out.annotation.partition_sizes
    assert sizes is not None
    assert out.annotation.partition_cv is not None
    mean = sum(sizes) / len(sizes)
    var = sum((s - mean) ** 2 for s in sizes) / len(sizes)
    cv = (var**0.5) / mean
    assert abs(cv - 1.5) / 1.5 <= 0.05
    assert abs(out.annotation.partition_cv - cv) < 1e-9


def test_composition_order_changes_corpus_but_stays_deterministic() -> None:
    base = _base_state(n=300, seed=9)

    def path_a(s: CorpusState) -> CorpusState:
        s = apply_churn(s, delete_fraction=0.1, skew=1.0, seed=1)
        s = inject_hubs(s, n_hubs=2, strength=3.0, seed=2)
        return inject_antihubs(s, n_antihubs=2, distance_factor=5.0, seed=3)

    def path_b(s: CorpusState) -> CorpusState:
        s = inject_hubs(s, n_hubs=2, strength=3.0, seed=2)
        s = inject_antihubs(s, n_antihubs=2, distance_factor=5.0, seed=3)
        return apply_churn(s, delete_fraction=0.1, skew=1.0, seed=1)

    a1, a2 = path_a(base), path_a(base)
    b1 = path_b(base)
    assert a1.vectors.tobytes() == a2.vectors.tobytes()
    assert a1.deleted.tobytes() == a2.deleted.tobytes()
    different = (
        a1.vectors.tobytes() != b1.vectors.tobytes()
        or a1.deleted.tobytes() != b1.deleted.tobytes()
    )
    assert different
    assert a1.annotation.dfi == 0.1
    assert len(a1.annotation.hub_ids) == 2
    assert len(a1.annotation.antihub_ids) == 2


def test_inject_antihubs_records_fraction_bound() -> None:
    state = _base_state(n=200, seed=4)
    out = inject_antihubs(state, n_antihubs=5, distance_factor=8.0, seed=8)
    assert len(out.annotation.antihub_ids) == 5
    assert out.annotation.antihub_fraction_lower_bound == 5 / out.ids.shape[0]


def test_operators_do_not_mutate_inputs() -> None:
    state = _base_state(n=100, seed=6)
    vec_before = state.vectors.tobytes()
    del_before = state.deleted.tobytes()
    apply_churn(state, delete_fraction=0.15, skew=0.0, seed=0)
    inject_hubs(state, n_hubs=1, strength=2.0, seed=0)
    inject_antihubs(state, n_antihubs=1, distance_factor=3.0, seed=0)
    skew_partitions(state, growth_factor=1.5, seed=0)
    assert state.vectors.tobytes() == vec_before
    assert state.deleted.tobytes() == del_before
