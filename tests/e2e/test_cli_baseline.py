"""E2E tests for vhecfsck baseline CLI subcommands and options (P8-03)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
from vhecfsck.cli import app
from vhecfsck.errors import ExitCode

runner = CliRunner()


def test_cli_baseline_record_and_audit(tmp_path: Path) -> None:
    """Record baseline to JSON, then audit against baseline cleanly."""
    baseline_file = tmp_path / "baseline.json"

    # 1. Record baseline
    res_rec = runner.invoke(
        app,
        [
            "baseline",
            "record",
            "synthetic://healthy?size=tiny",
            "--output",
            str(baseline_file),
            "--seed",
            "42",
        ],
    )
    assert res_rec.exit_code == int(ExitCode.OK), res_rec.output
    assert baseline_file.exists()

    # 2. Audit against baseline
    res_audit = runner.invoke(
        app,
        [
            "audit",
            "synthetic://healthy?size=tiny",
            "--baseline",
            str(baseline_file),
            "--seed",
            "42",
            "--gate",
            "both",
            "--format",
            "json",
        ],
    )
    assert res_audit.exit_code == int(ExitCode.OK), res_audit.output
    data = json.loads(res_audit.stdout)
    assert "baseline_delta" in data
    assert data["baseline_delta"]["comparable"] is True
    assert data["verdict"] == "OK"


def test_cli_baseline_mismatch_exits_3(tmp_path: Path) -> None:
    """Audit with mismatched seed exits 3 with not_comparable error."""
    baseline_file = tmp_path / "baseline.json"

    # Record with seed 42
    res_rec = runner.invoke(
        app,
        [
            "baseline",
            "record",
            "synthetic://healthy?size=tiny",
            "--output",
            str(baseline_file),
            "--seed",
            "42",
        ],
    )
    assert res_rec.exit_code == int(ExitCode.OK)

    # Audit with seed 999
    res_audit = runner.invoke(
        app,
        [
            "audit",
            "synthetic://healthy?size=tiny",
            "--baseline",
            str(baseline_file),
            "--seed",
            "999",
        ],
    )
    assert res_audit.exit_code == int(ExitCode.INCONCLUSIVE)
    assert "not_comparable" in res_audit.stderr


def test_cli_baseline_record_warns_on_degraded_index(tmp_path: Path) -> None:
    """Recording a baseline from a degraded index emits warning to stderr."""
    baseline_file = tmp_path / "baseline_degraded.json"

    res_rec = runner.invoke(
        app,
        [
            "baseline",
            "record",
            "synthetic://tombstoned?size=tiny",
            "--output",
            str(baseline_file),
            "--seed",
            "42",
        ],
    )
    # tombstoned has WARN/FAIL verdict
    assert "Warning" in res_rec.stderr or "warning" in res_rec.stderr.lower()
    assert baseline_file.exists()
