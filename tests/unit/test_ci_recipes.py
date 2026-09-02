"""Unit tests for CI integration recipes and composite actions (P9-03)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = ROOT / "examples"
ACTIONS_DIR = ROOT / ".github" / "actions" / "vhecfsck"


def test_composite_action_file_exists_and_valid() -> None:
    action_file = ACTIONS_DIR / "action.yml"
    assert action_file.exists()
    data = yaml.safe_load(action_file.read_text(encoding="utf-8"))
    assert data["name"] == "vhecfsck Vector Index Audit"
    assert "runs" in data
    assert data["runs"]["using"] == "composite"
    assert "inputs" in data
    assert "target" in data["inputs"]


def test_gitlab_ci_example_exists_and_valid() -> None:
    file_path = EXAMPLES_DIR / "gitlab-ci.yml"
    assert file_path.exists()
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    assert "vector_index_audit" in data
    assert "script" in data["vector_index_audit"]


def test_k8s_cronjob_example_exists_and_valid() -> None:
    file_path = EXAMPLES_DIR / "k8s-cronjob.yaml"
    assert file_path.exists()
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    assert data["kind"] == "CronJob"
    assert data["metadata"]["name"] == "vhecfsck-vector-audit"


def test_crontab_example_exists() -> None:
    file_path = EXAMPLES_DIR / "crontab.example"
    assert file_path.exists()
    text = file_path.read_text(encoding="utf-8")
    assert "vhecfsck audit" in text


def test_airflow_dag_example_exists_and_valid() -> None:
    file_path = EXAMPLES_DIR / "airflow_dag.py"
    assert file_path.exists()
    text = file_path.read_text(encoding="utf-8")
    assert "vhecfsck_vector_index_audit" in text
    assert "BashOperator" in text


def test_dagster_job_example_exists_and_valid() -> None:
    file_path = EXAMPLES_DIR / "dagster_job.py"
    assert file_path.exists()
    text = file_path.read_text(encoding="utf-8")
    assert "vhecfsck_audit_job" in text
    assert "@op" in text


def test_composite_action_workflow_exists_and_valid() -> None:
    workflow_file = ROOT / ".github" / "workflows" / "test-composite-action.yml"
    assert workflow_file.exists()
    data = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
    assert data["name"] == "Test Composite Action"


def test_release_workflow_uses_protected_pypi_environment() -> None:
    """P9-12: OIDC publish is gated on GitHub environment ``pypi``, no password."""
    workflow_file = ROOT / ".github" / "workflows" / "release.yml"
    data = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
    assert data["permissions"]["id-token"] == "write"
    job = data["jobs"]["verify-and-build"]
    assert job["environment"]["name"] == "pypi"
    assert job["environment"]["url"] == "https://pypi.org/p/vhecfsck"
    publish = next(
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish")
    )
    assert "password" not in publish.get("with", {})
