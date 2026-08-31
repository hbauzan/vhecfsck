"""E2E tests for vhecfsck serve command and --serve flag (P4-06)."""

from __future__ import annotations

import subprocess
import sys

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
    """FastAPI create_app serves the SPA index.html at GET /."""
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from vhecfsck.server.app import create_app

    server_app = create_app(target_uri="synthetic://healthy")
    client = TestClient(server_app)
    response = client.get("/")
    assert response.status_code == 200
    assert "vhecfsck" in response.text
