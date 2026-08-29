"""Smoke coverage for the installable CLI stub (needed for the overall floor)."""

from __future__ import annotations

import runpy
import sys

import pytest
from typer.testing import CliRunner
from vhecfsck.cli import app, main


def test_cli_help_exits_zero() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "vhecfsck" in result.stdout.lower()


def test_main_entrypoint_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["vhecfsck", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code in {0, None}


def test_module_entrypoint_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["vhecfsck", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("vhecfsck", run_name="__main__")
    assert excinfo.value.code in {0, None}
