"""P0-04: make verify target surface (gate itself is run outside this module)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_makefile_declares_required_targets() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "verify:",
        "verify-full:",
        "lint:",
        "format-check:",
        "typecheck:",
        "test:",
        "coverage:",
        "layers:",
        "readonly:",
        "fmt:",
        "test-fast:",
        "clean:",
        "web-build:",
        "demo:",
    ):
        assert target in text, f"Makefile missing target {target}"


def test_lint_substep_fails_on_unused_import(tmp_path: Path) -> None:
    """Gate composition: a failing lint recipe is non-zero (verify aggregates this)."""
    probe = tmp_path / "bad.py"
    probe.write_text("import os\nimport sys\n", encoding="utf-8")
    result = subprocess.run(
        ["uv", "run", "ruff", "check", str(probe)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
