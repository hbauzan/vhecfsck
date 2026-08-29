"""P0-08: import-layering contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_lint_imports_passes() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "importlinter.cli"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    # Prefer the console script if the module path differs.
    if result.returncode != 0 and "No module named" in (result.stderr + result.stdout):
        result = subprocess.run(
            ["uv", "run", "lint-imports"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr


def test_core_importing_adapters_fails_the_gate() -> None:
    probe = ROOT / "vhecfsck" / "core" / "_p0_08_layer_probe.py"
    probe.write_text("import vhecfsck.adapters  # noqa: F401\n", encoding="utf-8")
    try:
        result = subprocess.run(
            ["uv", "run", "lint-imports"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, result.stdout + result.stderr
    finally:
        probe.unlink(missing_ok=True)
