"""E2E tests for vhecfsck serve command and --serve flag (P4-06)."""

from __future__ import annotations

import typer.testing
from vhecfsck.cli import app
from vhecfsck.errors import ExitCode

runner = typer.testing.CliRunner()


def test_serve_missing_extra_raises_usage_error() -> None:
    """When fastapi/uvicorn missing, serve exits with USAGE (code 4)."""
    args = ["serve", "--target", "synthetic://healthy", "--no-browser"]
    result = runner.invoke(app, args)
    assert result.exit_code == ExitCode.USAGE
    assert "pip install" in result.stdout or "pip install" in result.stderr
    assert "vhecfsck[server]" in result.stdout or "vhecfsck[server]" in result.stderr


def test_serve_help_option() -> None:
    """vhecfsck serve --help displays options cleanly."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == ExitCode.OK
    assert "--target" in result.stdout
    assert "--port" in result.stdout
    assert "--no-browser" in result.stdout
    assert "--report" in result.stdout
