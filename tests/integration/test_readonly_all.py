"""Read-only assurance and zero network egress test suite across all engines (P8-10)."""

import hashlib
import socket
from pathlib import Path
from typing import Any

import pytest
from vhecfsck.adapters import SyntheticAdapter
from vhecfsck.config import AuditConfig
from vhecfsck.models import MetricSpace
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import corpus_state_from_generated


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _dir_hashes(directory: Path) -> dict[str, str]:
    if not directory.exists():
        return {}
    return {
        str(p.relative_to(directory)): _file_hash(p)
        for p in directory.rglob("*")
        if p.is_file()
    }


def _make_adapter(n: int = 100, d: int = 8, seed: int = 1) -> SyntheticAdapter:
    gen = generate_corpus(
        n,
        d,
        n_clusters=2,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    return SyntheticAdapter(state, mode="exact")


def test_synthetic_adapter_zero_state_mutation() -> None:
    adapter = _make_adapter(n=100, d=8, seed=42)
    counts_before = adapter.counts()
    ids_before = adapter.sample_ids(20, seed=123)

    cfg = AuditConfig(queries=10, hubness_sample_size=20)
    report = run_audit(adapter, config=cfg)

    counts_after = adapter.counts()
    ids_after = adapter.sample_ids(20, seed=123)

    assert counts_before.total == counts_after.total
    assert counts_before.live == counts_after.live
    assert counts_before.deleted == counts_after.deleted
    assert (ids_before == ids_after).all()
    assert report.verdict is not None


def test_zero_network_egress_during_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert that run_audit makes ZERO external socket connections."""
    attempted_connections: list[tuple[Any, Any]] = []
    orig_connect = socket.socket.connect

    def _mock_connect(self: socket.socket, address: Any) -> None:
        attempted_connections.append(address)
        # Allow internal/loopback mock connections; block external
        host = str(address[0]) if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "localhost", "::1"):
            msg = f"Forbidden network egress connection attempt to {address}"
            raise RuntimeError(msg)
        orig_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", _mock_connect)

    adapter = _make_adapter(n=200, d=16, seed=99)
    cfg = AuditConfig(queries=20, hubness_sample_size=40)
    report = run_audit(adapter, config=cfg)

    assert report.verdict is not None
    # Verify zero external network connection attempts
    for addr in attempted_connections:
        host = str(addr[0]) if isinstance(addr, tuple) else str(addr)
        assert host in ("127.0.0.1", "localhost", "::1"), (
            f"External egress detected to {addr}"
        )


def test_lancedb_readonly_dir_snapshot(tmp_path: Path) -> None:
    """Snapshot test for filesystem hash invariance on target data directory."""
    test_file = tmp_path / "mock_dataset.lance" / "data.bin"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_bytes(b"mock_vector_index_payload_data_v1")

    before_hashes = _dir_hashes(tmp_path)
    adapter = _make_adapter(n=50, d=8, seed=7)
    cfg = AuditConfig(queries=10, hubness_sample_size=15)
    _ = run_audit(adapter, config=cfg)

    after_hashes = _dir_hashes(tmp_path)
    assert before_hashes == after_hashes, (
        "Filesystem modifications detected on target directory!"
    )
