"""End-to-end tests for vhecfsck export CLI command (P3-07)."""

import json
from pathlib import Path

from typer.testing import CliRunner
from vhecfsck.cli import app

GOLDEN_DIR = Path(__file__).parents[1] / "fixtures" / "golden"


def test_cli_export_markdown_from_golden() -> None:
    golden_file = GOLDEN_DIR / "report-tombstoned.json"
    result = CliRunner().invoke(
        app, ["export", "--report", str(golden_file), "--format", "markdown"]
    )
    assert result.exit_code == 2
    assert "## 🔴 Vector Index Audit Report: FAIL" in result.stdout
    assert "| `canary_recall` |" in result.stdout


def test_cli_export_prometheus_from_golden() -> None:
    golden_file = GOLDEN_DIR / "report-healthy.json"
    result = CliRunner().invoke(
        app, ["export", "--report", str(golden_file), "--format", "prometheus"]
    )
    assert result.exit_code == 0
    assert "vhecfsck_up" in result.stdout
    assert "vhecfsck_canary_recall" in result.stdout


def test_cli_export_future_major_version_raises_usage(tmp_path: Path) -> None:
    future_report = tmp_path / "future_report.json"
    golden_file = GOLDEN_DIR / "report-healthy.json"
    data = json.loads(golden_file.read_text(encoding="utf-8"))
    data["schema_version"] = "2.0"
    future_report.write_text(json.dumps(data), encoding="utf-8")

    result = CliRunner().invoke(app, ["export", "--report", str(future_report)])
    assert result.exit_code == 4
    assert "unsupported report schema_version '2.0'" in result.stderr


def test_cli_export_nonexistent_file_raises_usage() -> None:
    result = CliRunner().invoke(app, ["export", "--report", "/nonexistent/report.json"])
    assert result.exit_code == 4
    assert "report file not found" in result.stderr
