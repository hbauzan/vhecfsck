"""Unit tests for programmatic documentation generators and site build (P9-02)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.generate_cli_docs import generate_cli_docs
from scripts.generate_metrics_docs import generate_metrics_docs
from scripts.generate_schema_docs import generate_schema_docs

ROOT = Path(__file__).resolve().parents[2]


def test_generate_cli_docs_structure() -> None:
    content = generate_cli_docs()
    assert "# CLI Reference" in content
    assert "## Overview" in content
    assert "## Commands" in content
    assert "### `vhecfsck audit`" in content
    assert "### `vhecfsck demo`" in content
    assert "### `vhecfsck export`" in content
    assert "### `vhecfsck serve`" in content
    assert "### `vhecfsck baseline`" in content


def test_generate_schema_docs_structure() -> None:
    content = generate_schema_docs()
    assert "# Report Schema Reference" in content
    assert "## Overview" in content
    assert "## Model Definitions" in content
    assert "Report" in content
    assert "MetricResult" in content
    assert "## Full JSON Schema Raw Dump" in content


def test_generate_metrics_docs_cites_spec_sections() -> None:
    content = generate_metrics_docs()
    assert "# Metrics Reference Specification" in content
    assert "Every metric definition cites its normative section" in content
    assert "*Cites `roadmap/02-metrics-spec.md` —" in content
    assert "`02-metrics-spec.md` §2.1" in content
    assert "`02-metrics-spec.md` §3.1" in content
    assert "`02-metrics-spec.md` §4.1" in content


def test_mkdocs_yml_exists_and_valid() -> None:
    mkdocs_file = ROOT / "mkdocs.yml"
    assert mkdocs_file.exists()
    text = mkdocs_file.read_text(encoding="utf-8")
    assert "site_name: vhecfsck" in text
    assert "theme:" in text
    assert "material" in text


def test_mkdocs_build_strict_smoke() -> None:
    """Smoke test running reference generators and mkdocs build --strict."""
    gen_cli = subprocess.run(
        ["uv", "run", "python", "scripts/generate_cli_docs.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert gen_cli.returncode == 0, gen_cli.stderr

    gen_schema = subprocess.run(
        ["uv", "run", "python", "scripts/generate_schema_docs.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert gen_schema.returncode == 0, gen_schema.stderr

    gen_metrics = subprocess.run(
        ["uv", "run", "python", "scripts/generate_metrics_docs.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert gen_metrics.returncode == 0, gen_metrics.stderr

    build = subprocess.run(
        ["uv", "run", "mkdocs", "build", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
