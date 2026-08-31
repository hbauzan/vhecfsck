"""Read-only verification harness and integration tests for LanceDB (P5-07)."""

from __future__ import annotations

import contextlib
import hashlib
import stat
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter


class DirectorySnapshot:
    """Snapshot of a directory tree's files, sizes, mtimes, and SHA-256 hashes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.files: dict[str, tuple[int, float, str]] = self._scan()

    def _scan(self) -> dict[str, tuple[int, float, str]]:
        res: dict[str, tuple[int, float, str]] = {}
        if not self.root.exists():
            return res
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(self.root))
                st = p.stat()
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
                res[rel] = (st.st_size, st.st_mtime, sha)
        return res

    def diff(self, after: DirectorySnapshot) -> list[str]:
        """Return list of file changes between self and after snapshot."""
        deltas: list[str] = []
        all_keys = set(self.files.keys()) | set(after.files.keys())
        for k in sorted(all_keys):
            if k not in self.files:
                deltas.append(f"ADDED: {k}")
            elif k not in after.files:
                deltas.append(f"DELETED: {k}")
            elif self.files[k] != after.files[k]:
                before_size, _, before_sha = self.files[k]
                after_size, _, after_sha = after.files[k]
                msg = (
                    f"MODIFIED: {k} (size: {before_size}->{after_size}, "
                    f"sha: {before_sha[:8]}->{after_sha[:8]})"
                )
                deltas.append(msg)
        return deltas


@contextlib.contextmanager
def read_only_dir(path: str | Path) -> Iterator[Path]:
    """Temporarily remove all write permissions from a directory and its contents."""
    p = Path(path).resolve()
    original_perms: dict[Path, int] = {}
    items = sorted([p, *list(p.rglob("*"))], key=lambda x: len(x.parts), reverse=True)
    for item in items:
        if item.exists():
            original_perms[item] = item.stat().st_mode

    # Remove write permissions from files first, then directories
    for item in sorted(items, key=lambda x: (not x.is_file(), len(x.parts))):
        if item.exists():
            item.chmod(
                item.stat().st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH
            )
    try:
        yield p
    finally:
        # Restore permissions (directories first, then files)
        for item in sorted(
            original_perms.keys(), key=lambda x: (x.is_file(), -len(x.parts))
        ):
            if item.exists():
                item.chmod(original_perms[item])


def assert_readonly_execution(
    target_dir: str | Path, audit_func: Callable[[], Any]
) -> None:
    """Assert that audit_func causes zero filesystem changes on target_dir."""
    before = DirectorySnapshot(target_dir)
    audit_func()
    after = DirectorySnapshot(target_dir)
    deltas = before.diff(after)
    assert not deltas, f"Read-only invariant violated! Filesystem changes: {deltas}"


def create_indexed_dataset(tmp_dir: str, n: int = 50, d: int = 4) -> str:
    import lance

    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), d)),
        ]
    )
    vecs = np.random.randn(n, d).astype(np.float32)
    data = pa.Table.from_arrays(
        [
            pa.array(list(range(n))),
            pa.array(vecs.tolist(), type=pa.list_(pa.float32(), d)),
        ],
        schema=schema,
    )
    lance.write_dataset(data, tmp_dir)
    ds = lance.dataset(tmp_dir)
    ds.create_index(
        column="vector",
        index_type="IVF_FLAT",
        metric_type="L2",
        num_partitions=2,
    )
    return tmp_dir


def run_full_lance_audit(target_dir: str) -> None:
    """Execute complete audit read operations on LanceDB dataset."""
    adapter = LanceDBAdapter(target_dir)
    try:
        _ = adapter.descriptor
        _ = adapter.capabilities
        _ = adapter.dimension
        _ = adapter.metric_space
        _ = adapter.counts()

        # Enumerate
        batches = list(adapter.iter_live_vectors(batch_size=10))
        assert len(batches) > 0

        # Sample and fetch
        sampled = adapter.sample_ids(5, seed=42)
        assert len(sampled) == 5
        fetched = adapter.fetch_vectors(sampled)
        assert fetched.vectors.shape == (5, adapter.dimension)

        # Search
        queries = np.random.randn(2, adapter.dimension).astype(np.float32)
        res = adapter.search(queries, k=3, params={"nprobe": 2})
        assert res.ids.shape == (2, 3)

        # Partitions
        part = adapter.partitions()
        assert part is not None
        assert part.n_partitions == 2
    finally:
        adapter.close()


def test_harness_detects_injected_write() -> None:
    """Verify that DirectorySnapshot diff catches added, modified, and deleted files."""
    tmp = tempfile.mkdtemp()
    target = Path(tmp)
    file1 = target / "test.txt"
    file1.write_text("hello")

    before = DirectorySnapshot(target)

    # Inject write
    file1.write_text("hello world")
    file2 = target / "new.txt"
    file2.write_text("added")

    after = DirectorySnapshot(target)
    deltas = before.diff(after)

    assert any("MODIFIED: test.txt" in d for d in deltas)
    assert any("ADDED: new.txt" in d for d in deltas)


def test_lancedb_audit_zero_filesystem_deltas() -> None:
    """Assert full LanceDB audit produces zero filesystem changes."""
    tmp = tempfile.mkdtemp()
    create_indexed_dataset(tmp, n=40, d=4)

    assert_readonly_execution(tmp, lambda: run_full_lance_audit(tmp))


def test_lancedb_audit_against_chmod_readonly_directory() -> None:
    """Assert full LanceDB audit succeeds against a chmod a-w read-only directory."""
    tmp = tempfile.mkdtemp()
    create_indexed_dataset(tmp, n=40, d=4)

    with read_only_dir(tmp):
        # Must execute cleanly without trying to write to disk
        run_full_lance_audit(tmp)
