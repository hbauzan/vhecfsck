"""This repo's AGENTS.md is opt-out — the generator must not overwrite it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "sync_agents_md.py"
_AGENTS = _REPO / "AGENTS.md"


def test_opt_out_check_is_noop() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--check"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "opt-out" in result.stdout


def test_opt_out_write_refuses_and_leaves_agents_md() -> None:
    before = _AGENTS.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "opt-out" in result.stderr
    assert _AGENTS.read_text(encoding="utf-8") == before
