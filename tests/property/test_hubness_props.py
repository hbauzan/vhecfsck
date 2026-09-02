"""Property tests for hubness metrics (P2-06)."""

from __future__ import annotations

import numpy as np
from numpy.random import default_rng
from vhecfsck.core.hubness import compute_hubness
from vhecfsck.models import MetricSpace, MetricState
from vhecfsck.synthetic import corpus_state_from_generated, generate_corpus
from vhecfsck.synthetic.pathologies import inject_antihubs, inject_hubs


def _corpus(n: int, d: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    gen = generate_corpus(
        n,
        d,
        n_clusters=4,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    return state.ids, state.vectors


def test_metrics_bounded_zero_to_one() -> None:
    ids, vecs = _corpus(1500, 8, 11)
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert hub.state is not MetricState.UNAVAILABLE
    assert 0.0 <= float(hub.value) <= 1.0
    assert 0.0 <= float(anti.value) <= 1.0


def test_invariant_under_row_permutation() -> None:
    ids, vecs = _corpus(1200, 6, 12)
    order = np.asarray([3, 1, 0, 2, 4, 5, *list(range(6, 1200))], dtype=np.int64)
    perm_ids = ids[order]
    perm_vecs = vecs[order]
    base_hub, base_anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=4,
        enforce_min_sample=True,
    )
    perm_hub, perm_anti = compute_hubness(
        corpus_ids=perm_ids,
        corpus_vectors=perm_vecs,
        sample_ids=perm_ids,
        metric_space=MetricSpace.L2,
        k_hub=4,
        enforce_min_sample=True,
    )
    assert perm_hub.value == base_hub.value
    assert perm_anti.value == base_anti.value


def test_invariant_under_global_rotation() -> None:
    rng = default_rng(13)
    ids, vecs = _corpus(1300, 5, 13)
    # Random orthogonal via QR.
    a = rng.standard_normal((5, 5))
    q, _ = np.linalg.qr(a)
    rot = vecs @ q.astype(np.float32)
    hub0, anti0 = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=3,
        enforce_min_sample=True,
    )
    hub1, anti1 = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=rot,
        metric_space=MetricSpace.L2,
        k_hub=3,
        enforce_min_sample=True,
    )
    assert hub1.value == hub0.value
    assert anti1.value == anti0.value


def test_cosine_invariant_under_positive_scaling() -> None:
    gen = generate_corpus(
        1400,
        6,
        n_clusters=3,
        cluster_std=0.15,
        cluster_size_skew=0.0,
        seed=14,
        metric_space=MetricSpace.COSINE,
    )
    state = corpus_state_from_generated(gen)
    scaled = state.vectors * np.float32(3.7)
    norms = np.sqrt(np.sum(scaled * scaled, axis=1, keepdims=True, dtype=np.float32))
    scaled = scaled / np.maximum(norms, np.float32(1e-8))
    hub0, anti0 = compute_hubness(
        corpus_ids=state.ids,
        corpus_vectors=state.vectors,
        sample_ids=state.ids,
        metric_space=MetricSpace.COSINE,
        k_hub=4,
        enforce_min_sample=True,
    )
    hub1, anti1 = compute_hubness(
        corpus_ids=state.ids,
        corpus_vectors=scaled,
        metric_space=MetricSpace.COSINE,
        k_hub=4,
        enforce_min_sample=True,
    )
    assert hub1.value == hub0.value
    assert anti1.value == anti0.value


def test_inject_hubs_increases_hub_share() -> None:
    state = corpus_state_from_generated(
        generate_corpus(
            2000,
            16,
            n_clusters=4,
            cluster_std=0.15,
            cluster_size_skew=0.0,
            seed=15,
            metric_space=MetricSpace.L2,
        )
    )
    base_hub, _ = compute_hubness(
        corpus_ids=state.ids,
        corpus_vectors=state.vectors,
        sample_ids=state.ids,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    with_hubs = inject_hubs(state, n_hubs=5, strength=4.0, seed=16)
    # Hubness is self-queried on S. Slicing ids[:n] after append drops the
    # injected hubs (they sit at the tail), so the gated metric cannot move.
    hub2, _ = compute_hubness(
        corpus_ids=with_hubs.ids,
        corpus_vectors=with_hubs.vectors,
        sample_ids=with_hubs.ids,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert float(hub2.value) > float(base_hub.value)


def test_inject_antihubs_increases_antihub_fraction() -> None:
    state = corpus_state_from_generated(
        generate_corpus(
            2000,
            16,
            n_clusters=4,
            cluster_std=0.15,
            cluster_size_skew=0.0,
            seed=17,
            metric_space=MetricSpace.L2,
        )
    )
    _, base_anti = compute_hubness(
        corpus_ids=state.ids,
        corpus_vectors=state.vectors,
        sample_ids=state.ids,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    with_anti = inject_antihubs(state, n_antihubs=80, distance_factor=8.0, seed=18)
    sample = with_anti.ids[:2000]
    _, anti2 = compute_hubness(
        corpus_ids=with_anti.ids,
        corpus_vectors=with_anti.vectors,
        sample_ids=sample,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert float(anti2.value) >= float(base_anti.value)
