"""E2E tests for vhecfsck serve command and --serve flag (P4-06)."""

from __future__ import annotations

import subprocess
import sys

import pytest
import typer.testing
from vhecfsck.cli import app
from vhecfsck.errors import ExitCode

runner = typer.testing.CliRunner()


def test_serve_missing_extra_raises_usage_error() -> None:
    """When fastapi/uvicorn missing, serve exits with USAGE (code 4)."""
    code = (
        "import sys; "
        "sys.modules['fastapi'] = None; "
        "sys.modules['uvicorn'] = None; "
        "from vhecfsck.cli import main; "
        "sys.argv = ['vhecfsck', 'serve', '--target', "
        "'synthetic://healthy', '--no-browser']; "
        "main()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == ExitCode.USAGE
    combined = result.stdout + result.stderr
    assert "pip install" in combined
    assert "vhecfsck[server]" in combined


def test_serve_help_option() -> None:
    """vhecfsck serve --help displays options cleanly."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == ExitCode.OK
    assert "--target" in result.stdout
    assert "--port" in result.stdout
    assert "--no-browser" in result.stdout
    assert "--report" in result.stdout


def test_spa_static_serving() -> None:
    """FastAPI create_app serves the SPA index.html at GET / (200) or fallback (500)."""
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from pathlib import Path

    from fastapi.testclient import TestClient
    from vhecfsck.server.app import create_app

    dist_index = (
        Path(__file__).resolve().parents[2] / "vhecfsck" / "web" / "dist" / "index.html"
    )

    server_app = create_app(target_uri="synthetic://healthy")
    client = TestClient(server_app)
    response = client.get("/")
    if dist_index.is_file():
        assert response.status_code == 200
        assert "vhecfsck" in response.text
    else:
        assert response.status_code == 500
        assert "make web-build" in response.text


def test_spa_static_serving_fallback_when_dist_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When dist/index.html is missing, GET / serves HTTP 500 with actionable hint."""
    pytest.importorskip("fastapi")
    from pathlib import Path

    from fastapi.testclient import TestClient
    from vhecfsck.server.app import create_app

    orig_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == "index.html" and "dist" in self.parts:
            return False
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    server_app = create_app(target_uri="synthetic://healthy")
    client = TestClient(server_app)
    response = client.get("/")
    assert response.status_code == 500
    assert "make web-build" in response.text


def test_get_report_publishes_progress_event() -> None:
    """GET /api/report triggers audit progress updates and finishes at 100%."""
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from vhecfsck.server.app import create_app

    server_app = create_app(target_uri="synthetic://healthy")
    client = TestClient(server_app)

    # Initial progress before report fetch is idle
    progress_before = client.get("/api/progress").json()
    assert progress_before["stage"] == "idle"

    # Fetch report to trigger audit
    report_res = client.get("/api/report")
    assert report_res.status_code == 200

    # Progress after report fetch must be terminal (100%)
    progress_after = client.get("/api/progress").json()
    assert progress_after["fraction"] == 1.0
    assert progress_after["terminal"] is True
