"""P0-02: ruff + mypy configuration contracts.

These tests encode the ticket acceptance criteria as durable checks so a future
edit cannot silently drop a required select rule or the strict core packages.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"

REQUIRED_RUFF_SELECT = {
    "E",
    "F",
    "W",
    "I",
    "N",
    "UP",
    "B",
    "A",
    "C4",
    "SIM",
    "ARG",
    "PTH",
    "RUF",
}
STRICT_MYPY_MODULES = {
    "vhecfsck.core",
    "vhecfsck.core.*",
    "vhecfsck.models",
    "vhecfsck.models.*",
    "vhecfsck.adapters",
    "vhecfsck.adapters.*",
    "vhecfsck.synthetic",
    "vhecfsck.synthetic.*",
}


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_ruff_select_includes_required_rule_families() -> None:
    tool = _load_pyproject()["tool"]
    select = set(tool["ruff"]["lint"]["select"])
    missing = REQUIRED_RUFF_SELECT - select
    assert not missing, f"ruff lint.select missing: {sorted(missing)}"


def test_ruff_enables_ann_and_d_for_core_and_models() -> None:
    """ANN+D selected globally; suppressed outside core/ and models/."""
    lint = _load_pyproject()["tool"]["ruff"]["lint"]
    select = set(lint["select"])
    assert {"ANN", "D"} <= select, "ANN and D must be in lint.select"

    ignores = lint.get("per-file-ignores", {})
    for pattern, codes in ignores.items():
        code_set = set(codes)
        if "core" in pattern or "models" in pattern:
            assert not ({"ANN", "D"} <= code_set), f"{pattern} must not ignore ANN+D"
        elif pattern.startswith("vhecfsck/") or pattern.startswith("tests/"):
            assert {"ANN", "D"} <= code_set, f"{pattern} should ignore ANN+D"

    core_dir = ROOT / "vhecfsck" / "core"
    probe = core_dir / "_p0_02_ann_probe.py"
    probe.write_text('"""Probe."""\n\ndef bare(x):\n    return x\n', encoding="utf-8")
    try:
        core_ruff = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(probe)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert core_ruff.returncode != 0
        assert "ANN" in core_ruff.stdout or "ANN" in core_ruff.stderr
    finally:
        probe.unlink(missing_ok=True)


def test_mypy_enables_required_strictness_flags() -> None:
    mypy = _load_pyproject()["tool"]["mypy"]
    assert mypy.get("disallow_any_generics") is True
    assert mypy.get("warn_return_any") is True
    assert mypy.get("no_implicit_optional") is True
    assert mypy.get("warn_unused_ignores") is True


def test_mypy_python_version_follows_running_interpreter() -> None:
    """numpy 2.5.2 (uv.lock, python_full_version >= 3.12) uses PEP 695 `type` aliases.

    Pinning ``python_version = "3.11"`` makes mypy abort on
    ``numpy/__init__.pyi`` ("Type statement is only supported in Python 3.12
    and greater") before checking vhecfsck. Omit the key so the running
    interpreter is the target: 3.11 keeps the ADR-0002 language floor, 3.12
    can parse the stubs. Do not set ``ignore_missing_imports`` on numpy.
    """
    mypy = _load_pyproject()["tool"]["mypy"]
    assert "python_version" not in mypy


def test_mypy_strict_override_covers_core_models_adapters() -> None:
    overrides = _load_pyproject()["tool"]["mypy"]["overrides"]
    strict_modules: set[str] = set()
    for override in overrides:
        if override.get("strict") is True:
            modules = override.get("module", [])
            if isinstance(modules, str):
                modules = [modules]
            strict_modules.update(modules)
    missing = STRICT_MYPY_MODULES - strict_modules
    assert not missing, f"mypy strict override missing modules: {sorted(missing)}"


def test_ruff_check_and_format_are_clean() -> None:
    check = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr

    fmt = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr


def test_mypy_reports_zero_errors() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "vhecfsck"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mypy_rejects_untyped_function_in_core() -> None:
    """Acceptance: a deliberately untyped def under core/ must fail mypy."""
    core_dir = ROOT / "vhecfsck" / "core"
    assert core_dir.is_dir(), "vhecfsck.core package must exist for strict typing"
    probe = core_dir / "_p0_02_untyped_probe.py"
    assert not probe.exists(), f"leftover probe file: {probe}"
    probe.write_text("def deliberately_untyped(x):\n    return x\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "vhecfsck/core"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, "mypy should reject an untyped core function"
        assert "deliberately_untyped" in combined or "untyped" in combined.lower()
    finally:
        probe.unlink(missing_ok=True)
        cache = core_dir / "__pycache__"
        leftovers = cache.glob("_p0_02_untyped_probe*.pyc") if cache.is_dir() else []
        for leftover in leftovers:
            leftover.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "pkg",
    ["vhecfsck.core", "vhecfsck.models", "vhecfsck.adapters"],
)
def test_typed_packages_are_importable(pkg: str) -> None:
    __import__(pkg)
