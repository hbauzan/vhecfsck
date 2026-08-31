"""E2E tests for `vhecfsck audit` CLI command (P3-04)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
from vhecfsck.cli import app


def test_cli_audit_help_exits_zero() -> None:
    result = CliRunner().invoke(app, ["audit", "--help"])
    assert result.exit_code == 0
    assert "--target" in result.stdout
    assert "--format" in result.stdout
    assert "--only" in result.stdout
    assert "--filter" in result.stdout
    assert "--group-by" in result.stdout


def test_cli_audit_missing_target_exits_usage() -> None:
    result = CliRunner().invoke(app, ["audit"])
    assert result.exit_code == 4


def test_cli_audit_unknown_flag_exits_usage() -> None:
    result = CliRunner().invoke(
        app, ["audit", "--target", "synthetic://healthy", "--nonexistent-flag"]
    )
    assert result.exit_code == 4


def test_cli_audit_unknown_scheme_exits_usage() -> None:
    result = CliRunner().invoke(app, ["audit", "--target", "invalid_scheme://foo"])
    assert result.exit_code == 4


def test_cli_audit_both_only_and_skip_exits_usage() -> None:
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://healthy",
            "--only",
            "canary_recall",
            "--skip",
            "dfi",
        ],
    )
    assert result.exit_code == 4


def test_cli_audit_filter_and_group_by_exits_usage() -> None:
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://tiny",
            "--filter",
            "tenant_id=t0",
            "--group-by",
            "tenant_id",
        ],
    )
    assert result.exit_code == 4


def test_cli_audit_invalid_filter_exits_usage() -> None:
    result = CliRunner().invoke(
        app,
        ["audit", "--target", "synthetic://tiny", "--filter", "noequals"],
    )
    assert result.exit_code == 4


def test_cli_audit_invalid_only_metric_exits_usage() -> None:
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://healthy",
            "--only",
            "nonexistent_metric",
        ],
    )
    assert result.exit_code == 4


def test_cli_audit_invalid_skip_metric_exits_usage() -> None:
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://healthy",
            "--skip",
            "nonexistent_metric",
        ],
    )
    assert result.exit_code == 4


def test_cli_audit_healthy_scenario_exits_ok() -> None:
    result = CliRunner().invoke(app, ["audit", "--target", "synthetic://healthy"])
    assert result.exit_code == 0
    assert "AUDIT VERDICT: OK" in result.stdout


def test_cli_audit_drifted_scenario_exits_ok() -> None:
    result = CliRunner().invoke(app, ["audit", "--target", "synthetic://drifted"])
    assert result.exit_code == 0
    assert "AUDIT VERDICT: OK" in result.stdout


def test_cli_audit_tombstoned_scenario_exits_fail() -> None:
    result = CliRunner().invoke(app, ["audit", "--target", "synthetic://tombstoned"])
    assert result.exit_code == 2
    assert "AUDIT VERDICT: FAIL" in result.stdout


def test_cli_audit_tiny_scenario_exits_inconclusive() -> None:
    result = CliRunner().invoke(app, ["audit", "--target", "synthetic://tiny"])
    assert result.exit_code == 3
    assert "AUDIT VERDICT: INCONCLUSIVE" in result.stdout


def test_cli_audit_format_json() -> None:
    result = CliRunner().invoke(
        app,
        ["audit", "--target", "synthetic://healthy", "--format", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["schema_version"] == "1.1"
    assert data["verdict"] == "OK"
    assert "metrics" in data


def test_cli_audit_format_prometheus() -> None:
    result = CliRunner().invoke(
        app,
        ["audit", "--target", "synthetic://healthy", "--format", "prometheus"],
    )
    assert result.exit_code == 0
    assert "vhecfsck_up{" in result.stdout
    assert "vhecfsck_audit_verdict{" in result.stdout


def test_cli_audit_output_file(tmp_path: Path) -> None:
    out_file = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://healthy",
            "--format",
            "json",
            "--output",
            str(out_file),
        ],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "OK"


def test_cli_audit_only_canary_recall() -> None:
    result = CliRunner().invoke(
        app,
        [
            "audit",
            "--target",
            "synthetic://healthy",
            "--only",
            "canary_recall",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    metric_states = {m["id"]: m["state"] for m in data["metrics"]}
    assert metric_states["canary_recall"] == "OK"
    assert metric_states["dfi"] == "DISABLED"
    assert metric_states["hub_share_top1pct"] == "DISABLED"
