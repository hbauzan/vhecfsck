"""Two runs of the README capture must be byte-identical (P6-07)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "record_demo.py"


def _load():
    spec = importlib.util.spec_from_file_location("record_demo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_two_captures_are_byte_identical(tmp_path: Path) -> None:
    mod = _load()
    first = tmp_path / "a.gif"
    second = tmp_path / "b.gif"
    mod.capture(first, fps=4, width=64, height=36)
    mod.capture(second, fps=4, width=64, height=36)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes()[:6] == b"GIF89a"
    assert first.stat().st_size < 5 * 1024 * 1024


def test_write_gif_rejects_an_empty_frame_list(tmp_path: Path) -> None:
    mod = _load()
    try:
        mod.write_gif([], tmp_path / "empty.gif")
    except ValueError as exc:
        assert "no frames" in str(exc)
    else:
        raise AssertionError("expected ValueError")
