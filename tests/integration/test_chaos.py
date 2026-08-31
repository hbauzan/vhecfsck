"""Integration tests for concurrency and chaos (P8-06)."""

import threading
import time
from typing import Any

import pytest
from vhecfsck.adapters import SyntheticAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.errors import ExitCode, TargetConnectionError
from vhecfsck.models import MetricSpace
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import corpus_state_from_generated


def _make_adapter(n: int = 400, d: int = 16, seed: int = 1) -> SyntheticAdapter:
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


class FailingAdapter(SyntheticAdapter):
    """Synthetic adapter that simulates target crash / network drop during search."""

    def search(self, queries: Any, k: int, params: Any = None) -> Any:
        del queries, k, params
        msg = "Connection reset by peer"
        raise ConnectionError(msg)


def test_concurrent_writes_during_audit() -> None:
    adapter = _make_adapter(n=300, d=16, seed=42)
    stop_event = threading.Event()

    def _writer() -> None:
        idx = 0
        while not stop_event.is_set():
            time.sleep(0.002)
            if idx < adapter._deleted.shape[0]:
                adapter._deleted[idx] = True
                idx = (idx + 1) % adapter._deleted.shape[0]

    writer_thread = threading.Thread(target=_writer)
    writer_thread.start()
    try:
        cfg = AuditConfig(queries=20, hubness_sample_size=50)
        report = run_audit(adapter, config=cfg)
        assert report is not None
        assert report.tool_version != ""
    finally:
        stop_event.set()
        writer_thread.join()


def test_concurrent_compaction_no_crash() -> None:
    adapter = _make_adapter(n=300, d=16, seed=10)
    stop_event = threading.Event()

    def _compactor() -> None:
        while not stop_event.is_set():
            time.sleep(0.002)
            _ = adapter.counts()

    thread = threading.Thread(target=_compactor)
    thread.start()
    try:
        cfg = AuditConfig(queries=15, hubness_sample_size=30)
        report = run_audit(adapter, config=cfg)
        assert report.counts.total > 0
    finally:
        stop_event.set()
        thread.join()


def test_target_killed_mid_audit_raises_target_connection_error() -> None:
    gen = generate_corpus(
        100,
        16,
        n_clusters=2,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=7,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    adapter = FailingAdapter(state, mode="exact")
    cfg = AuditConfig(queries=10, hubness_sample_size=20)

    with pytest.raises(TargetConnectionError) as exc_info:
        run_audit(adapter, config=cfg)

    assert exc_info.value.exit_code == ExitCode.USAGE
    assert exc_info.value.exit_code == 4
    assert exc_info.value.code == "target_connection"
    assert "Target connection lost" in str(exc_info.value)
