"""End-to-end tests for vhecfsck demo CLI command (P3-05)."""

import json

from typer.testing import CliRunner
from vhecfsck.cli import app
from vhecfsck.synthetic.scenarios import SCENARIO_NAMES


def test_cli_demo_default_exits_fail() -> None:
    result = CliRunner().invoke(app, ["demo"])
    assert result.exit_code == 2
    assert "pgvector#244" in result.stderr
    assert "AUDIT VERDICT: FAIL" in result.stdout


def test_cli_demo_healthy_scenario_exits_ok() -> None:
    result = CliRunner().invoke(app, ["demo", "--scenario", "healthy"])
    assert result.exit_code == 0
    assert "AUDIT VERDICT: OK" in result.stdout


def test_cli_demo_unknown_scenario_exits_usage() -> None:
    result = CliRunner().invoke(app, ["demo", "--scenario", "nonexistent"])
    assert result.exit_code == 4
    assert "usage:" in result.stderr


def test_cli_demo_format_json() -> None:
    result = CliRunner().invoke(app, ["demo", "--format", "json"])
    assert result.exit_code == 2
    data = json.loads(result.stdout)
    assert data["verdict"] == "FAIL"
    assert data["schema_version"] == "1.1"
    assert "metrics" in data


def test_cli_demo_serve_flag_prints_note() -> None:
    result = CliRunner().invoke(app, ["demo", "--serve"])
    assert result.exit_code == 2
    assert "requires P4" in result.stderr


def test_cli_demo_all_scenarios_reachable() -> None:
    runner = CliRunner()
    expected_exit_codes = {
        "healthy": 0,
        "drifted": 0,
        "tombstoned": 2,
        "hubby": 1,
        "capability_limited": 3,
        "tiny": 3,
    }
    for scenario_name in SCENARIO_NAMES:
        res = runner.invoke(
            app, ["demo", "--scenario", scenario_name, "--size", "small"]
        )
        expected = expected_exit_codes[scenario_name]
        assert res.exit_code == expected, (
            f"Scenario {scenario_name} failed: exit {res.exit_code} != {expected}"
        )
