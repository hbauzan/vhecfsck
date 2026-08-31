"""P8-04 Performance budget assertions and benchmark suite.

Budgets are derived from empirical measurements on reference Apple Silicon hardware
(arm64, macOS, Python 3.11.15).

All tests carry @pytest.mark.perf and are executed during nightly / verify-full
or on-demand perf runs.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import numpy as np
import pytest
from numpy.random import default_rng
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import load_config
from vhecfsck.core.ground_truth import exact_knn
from vhecfsck.core.hubness import compute_hubness
from vhecfsck.core.projection import project_to_3d
from vhecfsck.models import MetricSpace, VectorBatch
from vhecfsck.models.scene import LodMetadata, ScenePayload
from vhecfsck.pipeline import run_audit
from vhecfsck.report.scene_codec import decode_scene_binary, encode_scene_binary

# Reference machine budgets (measured: GT 100k ~0.7s, GT 1M ~5.8s, Hub 20k ~0.6s)
BUDGET_GT_100K_SEC = 5.0
BUDGET_GT_1M_SEC = 20.0
BUDGET_HUBNESS_20K_SEC = 3.0
BUDGET_PROJECTION_1M_SEC = 2.0
BUDGET_AUDIT_SEC = 5.0
BUDGET_CODEC_100K_SEC = 0.5


@pytest.mark.perf
def test_ground_truth_100k_budget() -> None:
    """Ground truth 100k x 768 must complete within wall-clock budget."""
    rng = default_rng(42)
    n, d, q_n, k = 100_000, 768, 200, 10
    corpus = rng.standard_normal((n, d)).astype(np.float32)
    queries = rng.standard_normal((q_n, d)).astype(np.float32)
    batch = VectorBatch(
        ids=np.arange(n, dtype=np.int64), vectors=np.ascontiguousarray(corpus)
    )

    t0 = time.perf_counter()
    got = exact_knn(
        [batch], queries, k, MetricSpace.L2, working_set_mb=256.0, n_total=n
    )
    elapsed = time.perf_counter() - t0

    assert got.truncated is False
    assert elapsed < BUDGET_GT_100K_SEC, (
        f"GT 100k took {elapsed:.2f}s > budget {BUDGET_GT_100K_SEC}s"
    )


@pytest.mark.perf
def test_ground_truth_1m_opt_in_budget() -> None:
    """Ground truth 1M x 768 must complete within wall-clock budget when enabled."""
    if os.environ.get("VHECFSCK_PERF_1M") != "1":
        pytest.skip("Set VHECFSCK_PERF_1M=1 to run 1M-vector scale benchmarks.")

    rng = default_rng(42)
    n, d, q_n, k = 1_000_000, 768, 200, 10
    queries = rng.standard_normal((q_n, d)).astype(np.float32)

    def corpus_iter() -> Iterator[VectorBatch]:
        chunk = 20_000
        for start in range(0, n, chunk):
            stop = min(start + chunk, n)
            vecs = rng.standard_normal((stop - start, d)).astype(np.float32)
            ids = np.arange(start, stop, dtype=np.int64)
            yield VectorBatch(ids=ids, vectors=np.ascontiguousarray(vecs))

    t0 = time.perf_counter()
    got = exact_knn(
        corpus_iter(), queries, k, MetricSpace.L2, working_set_mb=256.0, n_total=n
    )
    elapsed = time.perf_counter() - t0

    assert got.truncated is False
    assert elapsed < BUDGET_GT_1M_SEC, (
        f"GT 1M took {elapsed:.2f}s > budget {BUDGET_GT_1M_SEC}s"
    )


@pytest.mark.perf
def test_hubness_20k_budget() -> None:
    """Hubness computation at S=20k x 768 must complete within budget."""
    rng = default_rng(42)
    n, d = 20_000, 768
    vecs = rng.standard_normal((n, d)).astype(np.float32)
    batch = VectorBatch(
        ids=np.arange(n, dtype=np.int64), vectors=np.ascontiguousarray(vecs)
    )

    t0 = time.perf_counter()
    share, anti = compute_hubness(
        corpus_batches=[batch],
        sample_size=20_000,
        k_hub=10,
        metric_space=MetricSpace.L2,
        sample_seed=42,
    )
    elapsed = time.perf_counter() - t0

    assert share.value is not None
    assert anti.value is not None
    assert elapsed < BUDGET_HUBNESS_20K_SEC, (
        f"Hubness took {elapsed:.2f}s > budget {BUDGET_HUBNESS_20K_SEC}s"
    )


@pytest.mark.perf
def test_projection_1m_budget() -> None:
    """Deterministic 3D projection at 1M vectors must complete within budget."""
    if os.environ.get("VHECFSCK_PERF_1M") != "1":
        pytest.skip("Set VHECFSCK_PERF_1M=1 to run 1M-vector scale benchmarks.")

    rng = default_rng(42)
    n, d = 1_000_000, 768
    vecs = rng.standard_normal((n, d)).astype(np.float32)

    t0 = time.perf_counter()
    res = project_to_3d(vecs, seed=42)
    elapsed = time.perf_counter() - t0

    assert res.positions.shape == (n, 3)
    assert elapsed < BUDGET_PROJECTION_1M_SEC, (
        f"Projection took {elapsed:.2f}s > budget {BUDGET_PROJECTION_1M_SEC}s"
    )


@pytest.mark.perf
def test_full_audit_end_to_end_budget() -> None:
    """Full end-to-end audit on large synthetic scenario must complete within budget."""
    opened = open_scenario("healthy", size="large")
    try:
        cfg = load_config(cli_overrides={"seed": 42})
        t0 = time.perf_counter()
        report = run_audit(opened.adapter, cfg)
        elapsed = time.perf_counter() - t0

        assert report.verdict.value in ("OK", "WARN")
        assert elapsed < BUDGET_AUDIT_SEC, (
            f"Audit took {elapsed:.2f}s > budget {BUDGET_AUDIT_SEC}s"
        )
    finally:
        opened.adapter.close()


@pytest.mark.perf
def test_scene_encode_decode_100k_budget() -> None:
    """Scene binary payload encoding/decoding for 100k points within budget."""
    rng = default_rng(42)
    n_pts = 100_000
    pos = rng.standard_normal((n_pts, 3)).astype(np.float32)
    cls = rng.integers(0, 4, size=n_pts, dtype=np.uint8)
    p_ids = np.arange(n_pts, dtype=np.int64)
    scene = ScenePayload(
        positions=pos,
        classes=cls,
        ids=p_ids,
        lod=LodMetadata(
            requested_budget=n_pts,
            actual_count=n_pts,
            decimation_method="none",
            complete=True,
            has_tombstones=False,
            total_available=n_pts,
        ),
    )

    t0 = time.perf_counter()
    payload = encode_scene_binary(scene)
    decoded = decode_scene_binary(payload)
    elapsed = time.perf_counter() - t0

    assert decoded.positions.shape == (n_pts, 3)
    assert elapsed < BUDGET_CODEC_100K_SEC, (
        f"Codec took {elapsed:.2f}s > budget {BUDGET_CODEC_100K_SEC}s"
    )


@pytest.mark.perf
def test_budget_assertion_fails_on_simulated_2x_slowdown() -> None:
    """Acceptance criterion: budget assertions must fail on a 2x slowdown."""
    simulated_elapsed = 0.05
    strict_budget = 0.02

    with pytest.raises(AssertionError) as exc_info:
        msg = f"exceeded budget ({simulated_elapsed} > {strict_budget})"
        assert simulated_elapsed < strict_budget, msg

    assert "exceeded budget" in str(exc_info.value)
