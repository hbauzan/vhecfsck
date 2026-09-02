"""Unit tests for `scripts/clean_orphans.py`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.clean_orphans import (
    ancestor_pids,
    clean_checkout_orphans,
    get_checkout_orphan_pids,
)

ROOT = Path(__file__).resolve().parents[2]


def test_clean_checkout_orphans_skips_in_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SETUP_SH_IN_TEST=1 or CLEAN_ORPHANS_IN_TEST=1 must skip signal delivery."""
    monkeypatch.setenv("SETUP_SH_IN_TEST", "1")
    assert clean_checkout_orphans() == 0


def test_get_checkout_orphan_pids_excludes_self() -> None:
    """get_checkout_orphan_pids must never return the current process or parent PID."""
    pids = get_checkout_orphan_pids(ROOT)
    assert os.getpid() not in pids
    assert os.getppid() not in pids


def test_get_checkout_orphan_pids_never_returns_ancestors() -> None:
    """Live scan: no ancestor of this process is a candidate."""
    pids = get_checkout_orphan_pids(ROOT)
    claimed = set(pids)
    ancestors = ancestor_pids(os.getpid())
    assert claimed.isdisjoint(ancestors)


def test_get_checkout_orphan_pids_skips_matching_shell_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parent shell with `cd <root> && make verify` on its cmdline is not an orphan.

    That is the P9-13 repro: excluding only self and getppid() left the shell two
    or three levels up eligible, and clean-proc SIGKILL'd the gate's own caller.
    """
    root = Path("/Users/hbauzan/treepwood/vhecfsck")
    table = [
        (1, 0, "/sbin/launchd"),
        (10, 1, f"/bin/zsh -c cd {root} && make verify"),
        (20, 10, "make verify"),
        (30, 20, f"uv run python {root}/scripts/clean_orphans.py"),
        (40, 1, f"{sys.executable} -c # pytest dummy runner for {root}"),
    ]
    monkeypatch.setattr("scripts.clean_orphans._read_process_table", lambda: table)
    monkeypatch.setattr(os, "getpid", lambda: 30)
    monkeypatch.setattr(os, "getppid", lambda: 20)

    pids = get_checkout_orphan_pids(root)

    assert 10 not in pids
    assert 20 not in pids
    assert 30 not in pids
    assert 40 in pids


def test_clean_checkout_orphans_terminates_dummy_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that an orphan background test process matching root is terminated."""
    monkeypatch.delenv("SETUP_SH_IN_TEST", raising=False)
    monkeypatch.delenv("CLEAN_ORPHANS_IN_TEST", raising=False)

    code = f"# pytest dummy runner for {tmp_path}\nimport time; time.sleep(30)"
    proc = subprocess.Popen([sys.executable, "-c", code])
    try:
        pids = get_checkout_orphan_pids(tmp_path)
        assert proc.pid in pids

        res = clean_checkout_orphans(tmp_path)
        assert res == 0

        proc.wait(timeout=2.0)
        assert proc.returncode != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
