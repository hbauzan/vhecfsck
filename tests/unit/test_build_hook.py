"""Tests for hatch custom build hook and wheel packaging (P4-11 / HYG-02)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
HATCH_BUILD = ROOT / "hatch_build.py"


def test_hatch_build_hook_declared_and_importable() -> None:
    """Fast static contract: pyproject declares hatch_build.py and CustomBuildHook."""
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)

    custom_hook = (
        data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("hooks", {})
        .get("custom", {})
    )
    assert custom_hook.get("path") == "hatch_build.py"

    wheel_artifacts = (
        data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("artifacts", [])
    )
    sdist_artifacts = (
        data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("sdist", {})
        .get("artifacts", [])
    )

    sdist_only_include = (
        data.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("sdist", {})
        .get("only-include", [])
    )

    assert "vhecfsck/web/dist" in wheel_artifacts
    assert "vhecfsck/web/dist" in sdist_artifacts
    assert "hatch_build.py" in sdist_only_include

    assert HATCH_BUILD.is_file()

    spec = importlib.util.spec_from_file_location("hatch_build", HATCH_BUILD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "CustomBuildHook")
    assert callable(getattr(mod.CustomBuildHook, "initialize", None))


def test_build_hook_initialize_skips_npm_when_dist_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When web/dist/index.html exists, initialize must not invoke npm."""
    dist_dir = tmp_path / "vhecfsck" / "web" / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!DOCTYPE html><html></html>", encoding="utf-8"
    )

    spec = importlib.util.spec_from_file_location("hatch_build", HATCH_BUILD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    hook = mod.CustomBuildHook(
        root=str(tmp_path),
        config={},
        build_config={},
        metadata={},
        directory=str(tmp_path),
        target_name="wheel",
    )

    subprocess_calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        subprocess_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/local/bin/npm")
    monkeypatch.setattr(subprocess, "run", fake_run)

    hook.initialize("0.1.0", {})
    assert not subprocess_calls, (
        f"Expected 0 subprocess calls when dist exists, got {subprocess_calls}"
    )


def test_build_hook_initialize_runs_npm_when_dist_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When dist/index.html is missing and npm exists, initialize runs npm build."""
    web_dir = tmp_path / "vhecfsck" / "web"
    web_dir.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location("hatch_build", HATCH_BUILD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    hook = mod.CustomBuildHook(
        root=str(tmp_path),
        config={},
        build_config={},
        metadata={},
        directory=str(tmp_path),
        target_name="wheel",
    )

    subprocess_calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        subprocess_calls.append(cmd)
        # Create index.html on build command so check passes
        if "build" in cmd:
            dist_dir = web_dir / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                "<!DOCTYPE html><html></html>", encoding="utf-8"
            )
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/local/bin/npm")
    monkeypatch.setattr(subprocess, "run", fake_run)

    hook.initialize("0.1.0", {})
    assert subprocess_calls == [
        ["/usr/local/bin/npm", "ci"],
        ["/usr/local/bin/npm", "run", "build"],
    ]


def test_build_hook_initialize_raises_when_dist_missing_and_no_npm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When dist/index.html missing and npm absent, initialize raises RuntimeError."""
    web_dir = tmp_path / "vhecfsck" / "web"
    web_dir.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location("hatch_build", HATCH_BUILD)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    hook = mod.CustomBuildHook(
        root=str(tmp_path),
        config={},
        build_config={},
        metadata={},
        directory=str(tmp_path),
        target_name="wheel",
    )

    monkeypatch.setattr(shutil, "which", lambda _cmd: None)

    with pytest.raises(RuntimeError, match="npm is required"):
        hook.initialize("0.1.0", {})


@pytest.mark.slow
def test_wheel_build_includes_web_dist(tmp_path: Path) -> None:
    """Slow integration smoke: building wheel packages vhecfsck/web/dist/index.html."""
    npm = shutil.which("npm")
    dist_html = ROOT / "vhecfsck" / "web" / "dist" / "index.html"
    if npm is None and not dist_html.is_file():
        pytest.skip("npm is not available on PATH and dist/index.html is not pre-built")

    out_dir = tmp_path / "wheel_out"
    out_dir.mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, (
        f"uv build failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    wheels = list(out_dir.glob("*.whl"))
    assert wheels, "No wheel artifact found in build output"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
        assert "vhecfsck/web/dist/index.html" in names
