"""Lock the skill-template footguns this repo already paid for."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO / ".agents" / "skills" / "dev-protocol" / "templates"


def test_ci_template_never_syncs_all_extras() -> None:
    text = (_TEMPLATES / "ci.yml").read_text(encoding="utf-8")
    sync_runs = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("- run:") and "uv sync" in line
    ]
    assert sync_runs, "ci.yml template should still run uv sync"
    assert all("--all-extras" not in line for line in sync_runs)


def test_github_workflows_never_sync_all_extras() -> None:
    workflows_dir = _REPO / ".github" / "workflows"
    workflow_files = list(workflows_dir.glob("*.yml")) + list(
        workflows_dir.glob("*.yaml")
    )
    assert workflow_files, "Should find workflow files in .github/workflows/"

    for wf_path in workflow_files:
        lines = wf_path.read_text(encoding="utf-8").splitlines()
        offending = [
            (idx + 1, line)
            for idx, line in enumerate(lines)
            if "uv sync" in line and "--all-extras" in line
        ]
        assert not offending, (
            f"Found '--all-extras' in 'uv sync' line in {wf_path.name}: {offending}"
        )


def test_makefile_template_coverage_is_one_instrumented_run() -> None:
    text = (_TEMPLATES / "Makefile").read_text(encoding="utf-8")
    cov_block = text.split("coverage:", 1)[1].split("\n\n", 1)[0]
    assert cov_block.count("pytest") == 1
    assert "--cov=" in cov_block
    assert "coverage report --include=" in cov_block
