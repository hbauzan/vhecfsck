"""P2-06: hubness metrics — Fixture B, differential oracle, guards, CORRECTION 3."""

from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.random import default_rng
from vhecfsck.core.hubness import (
    ANTIHUB_METRIC_ID,
    HUB_SHARE_METRIC_ID,
    antihub_fraction_from_nk,
    compute_hubness,
    count_nk_from_neighbour_ids,
    hub_share_top1pct_from_nk,
)
from vhecfsck.errors import InternalError
from vhecfsck.models import MetricSpace, MetricState, VectorBatch

from tests.oracle.reference import naive_nk


def _fixture_b() -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray([[0.0], [1.0], [2.0], [10.0]], dtype=np.float32)
    ids = np.arange(4, dtype=np.int64)
    return ids, points


def test_fixture_b_exact() -> None:
    """Fixture B — §3.7: N_k=[1,2,1,0], antihub=0.25, hub_share=0.5."""
    ids, points = _fixture_b()
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=points,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1,
        enforce_min_sample=False,
    )
    assert hub.id == HUB_SHARE_METRIC_ID
    assert anti.id == ANTIHUB_METRIC_ID
    n_k = np.asarray(hub.detail["n_k"], dtype=np.int64)
    assert n_k.tolist() == [1, 2, 1, 0]
    assert int(sum(int(x) for x in n_k)) == 4
    assert anti.value == 0.25
    assert hub.value == 0.5
    assert hub.sampling == anti.sampling
    assert hub.sampling["S"] == 4
    assert hub.sampling["k_hub"] == 1


@pytest.mark.parametrize("space", list(MetricSpace))
def test_differential_vs_naive_nk(space: MetricSpace) -> None:
    """Blocked hubness path matches naive_nk on randomised corpora (§3.1)."""
    rng = default_rng(20260829)
    for _ in range(12):
        n = int(rng.integers(8, 40))
        d = int(rng.integers(1, 6))
        k_hub = int(rng.integers(1, min(5, n)))
        raw = rng.standard_normal((n, d), dtype=np.float32)
        if space is MetricSpace.COSINE:
            norms = np.sqrt(np.sum(raw * raw, axis=1, keepdims=True, dtype=np.float32))
            norms = np.maximum(norms, np.float32(1e-8))
            corpus = raw / norms
        else:
            corpus = raw
        naive = naive_nk(corpus, k=k_hub, metric_space=space)
        hub, anti = compute_hubness(
            corpus_ids=np.arange(n, dtype=np.int64),
            corpus_vectors=corpus,
            sample_ids=np.arange(n, dtype=np.int64),
            metric_space=space,
            k_hub=k_hub,
            enforce_min_sample=False,
        )
        got = np.asarray(hub.detail["n_k"], dtype=np.int64)
        assert got.tolist() == naive.tolist()
        assert hub.value == pytest.approx(hub_share_top1pct_from_nk(naive))
        assert anti.value == pytest.approx(antihub_fraction_from_nk(naive))


def test_guard_s_below_1000_unavailable() -> None:
    ids = np.arange(500, dtype=np.int64)
    vecs = np.random.default_rng(1).standard_normal((500, 4), dtype=np.float32)
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert hub.state is MetricState.UNAVAILABLE
    assert anti.state is MetricState.UNAVAILABLE
    assert hub.value is None
    assert "1000" in (hub.unavailable_reason or "")


def test_guard_k_hub_ge_s_unavailable() -> None:
    ids = np.arange(1200, dtype=np.int64)
    vecs = np.random.default_rng(2).standard_normal((1200, 4), dtype=np.float32)
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1200,
        enforce_min_sample=True,
    )
    assert hub.state is MetricState.UNAVAILABLE
    assert anti.state is MetricState.UNAVAILABLE


def test_degenerate_all_identical() -> None:
    """§3.6 case 6: equal N_k → antihub=0, hub_share=0.01."""
    s = 1000
    ids = np.arange(s, dtype=np.int64)
    vecs = np.ones((s, 8), dtype=np.float32)
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=s - 1,
        enforce_min_sample=True,
    )
    assert anti.value == 0.0
    assert hub.value == pytest.approx(math.ceil(0.01 * s) / s)
    n_k = np.asarray(hub.detail["n_k"], dtype=np.int64)
    assert int(np.min(n_k)) == int(np.max(n_k))


def test_invariant_violation_raises_internal_error() -> None:
    """§3.6 case 7: sum(N_k) != S*k_hub → InternalError."""
    ids = np.arange(4, dtype=np.int64)
    # k_hub=2 but only one neighbour per row → sum(N_k)=4 != 4*2=8.
    neighbours = np.asarray(
        [[1, -1], [0, -1], [1, -1], [2, -1]],
        dtype=np.int64,
    )
    with pytest.raises(InternalError, match="sum\\(N_k\\)"):
        count_nk_from_neighbour_ids(
            neighbours,
            sample_ids=ids,
            k_hub=2,
            assert_invariant=True,
        )


def test_engine_source_same_counting_code() -> None:
    """--hubness-source engine reuses counting over supplied neighbour ids."""
    ids, points = _fixture_b()
    truth_hub, _ = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=points,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1,
        hubness_source="truth",
        enforce_min_sample=False,
    )
    # Engine returns identical neighbours (exact search stand-in).
    neighbours = np.full((4, 1), -1, dtype=np.int64)
    for qi in range(4):
        scored: list[tuple[float, int]] = []
        for ci in range(4):
            if ci == qi:
                continue
            dist = abs(float(points[ci, 0] - points[qi, 0]))
            scored.append((dist, ci))
        scored.sort(key=lambda t: (t[0], t[1]))
        neighbours[qi, 0] = scored[0][1]
    eng_hub, eng_anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=points,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1,
        hubness_source="engine",
        engine_neighbour_ids=neighbours,
        enforce_min_sample=False,
    )
    assert eng_hub.value == truth_hub.value
    assert eng_anti.value == pytest.approx(0.25)


def test_thresholds_uncalibrated_flag() -> None:
    ids = np.arange(1500, dtype=np.int64)
    vecs = np.random.default_rng(3).standard_normal((1500, 4), dtype=np.float32)
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=7,
        enforce_min_sample=True,
    )
    assert hub.detail["thresholds_uncalibrated_for_sample_size"] is True
    assert anti.detail["thresholds_uncalibrated_for_sample_size"] is True


def test_diagnostics_present() -> None:
    ids, points = _fixture_b()
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=points,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1,
        enforce_min_sample=False,
    )
    for result in (hub, anti):
        detail = result.detail
        assert "max_nk" in detail
        assert "p99_nk" in detail
        assert "median_nk" in detail
        assert "histogram" in detail
        assert "hub_outlier_count" in detail
        assert "hub_ids" in detail
        assert "antihub_ids" in detail
        assert "duplicate_vector_pairs" in detail
        assert "norm_p99_ratio" in detail
    assert hub.detail["antihub_ids"] == [3]
    assert hub.detail["hub_ids"][0] == 1


def test_correction3_healthy_50k_not_antihub_saturated() -> None:
    """CORRECTION 3: independent S must not yield antihub≈1 on healthy 50k."""
    from vhecfsck.synthetic import corpus_state_from_generated, generate_corpus

    gen = generate_corpus(
        50_000,
        32,
        n_clusters=8,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=42,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    ids = state.ids
    vecs = state.vectors
    hub, anti = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        metric_space=MetricSpace.L2,
        sample_size=20_000,
        sample_seed=99,
        k_hub=10,
        enforce_min_sample=True,
    )
    assert anti.state is not MetricState.UNAVAILABLE
    assert float(anti.value) < 0.5
    assert hub.sampling["S"] == 20_000
    # Canary Q=200 on same corpus must not be the hubness sample.
    assert hub.sampling.get("decoupled_from_canary") is True


def test_live_corpus_smaller_than_requested_s() -> None:
    """§3.6 case 4: use whole corpus when smaller than requested S."""
    ids = np.arange(1500, dtype=np.int64)
    vecs = np.random.default_rng(4).standard_normal((1500, 3), dtype=np.float32)
    hub, _ = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        metric_space=MetricSpace.L2,
        sample_size=20_000,
        sample_seed=1,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert hub.sampling["S"] == 1500


def test_dot_norm_p99_ratio_reported() -> None:
    rng = default_rng(5)
    n = 1200
    vecs = rng.standard_normal((n, 4), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.maximum(norms, 1e-8)
    vecs[-50:] *= 10.0
    ids = np.arange(n, dtype=np.int64)
    hub, _ = compute_hubness(
        corpus_ids=ids,
        corpus_vectors=vecs,
        sample_ids=ids,
        metric_space=MetricSpace.DOT,
        k_hub=5,
        enforce_min_sample=True,
    )
    assert float(hub.detail["norm_p99_ratio"]) > 1.0


def test_blocked_path_via_batches() -> None:
    """Hubness works when corpus arrives as streamed batches."""
    ids, points = _fixture_b()
    batches = [VectorBatch(ids=ids, vectors=points)]
    hub, anti = compute_hubness(
        corpus_batches=batches,
        sample_ids=ids,
        metric_space=MetricSpace.L2,
        k_hub=1,
        enforce_min_sample=False,
    )
    assert hub.value == 0.5
    assert anti.value == 0.25
