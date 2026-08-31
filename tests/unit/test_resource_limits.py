"""Unit tests for resource limits, memory degradation, and deadlines (P8-05)."""

import pytest
from vhecfsck.adapters import SyntheticAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.errors import ResourceError
from vhecfsck.models import MetricSpace
from vhecfsck.pipeline import _degrade_sampling, run_audit
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import corpus_state_from_generated


def _make_adapter(n: int = 500, d: int = 32, seed: int = 42) -> SyntheticAdapter:
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
    return SyntheticAdapter(state, mode="exact")


def test_degrade_sampling_valid_scaling() -> None:
    cfg = AuditConfig(queries=200, hubness_sample_size=20_000, max_memory_mb=1.0)
    # Need: 100k vectors * 128 dim * 4 bytes = 51.2 MB. Budget = 1 MB. Scale ~ 0.0195
    degraded = _degrade_sampling(cfg, n_live=100_000, dimension=128)
    assert degraded.queries < 200
    assert degraded.hubness_sample_size < 20_000
    assert degraded.queries >= 5
    assert degraded.hubness_sample_size >= 100


def test_degrade_sampling_impossible_memory_raises_resource_error() -> None:
    cfg = AuditConfig(max_memory_mb=0.00001)
    with pytest.raises(ResourceError) as exc_info:
        _degrade_sampling(cfg, n_live=100_000, dimension=128)
    assert "below minimum required allocation" in str(exc_info.value)
    assert exc_info.value.code == "resource_limit"


def test_degrade_sampling_negative_memory_raises_resource_error() -> None:
    cfg = AuditConfig(max_memory_mb=-5.0)
    with pytest.raises(ResourceError):
        _degrade_sampling(cfg, n_live=1000, dimension=16)


def test_run_audit_records_peak_rss_mb() -> None:
    adapter = _make_adapter(n=100, d=8, seed=42)
    cfg = AuditConfig(queries=10, hubness_sample_size=20)
    report = run_audit(adapter, config=cfg)
    assert report.run.peak_rss_mb is not None
    assert report.run.peak_rss_mb > 0.0


def test_run_audit_degraded_warning_emitted() -> None:
    adapter = _make_adapter(n=500, d=32, seed=42)
    # Budget = 0.02 MB (20 KB) forces scale down (Need = 500 * 32 * 4 = 64 KB)
    cfg = AuditConfig(queries=100, hubness_sample_size=400, max_memory_mb=0.02)
    report = run_audit(adapter, config=cfg)
    assert any("sampling_degraded_for_memory_budget" in w for w in report.warnings)
