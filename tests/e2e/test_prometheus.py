"""End-to-end tests for Prometheus exporter renderer (P3-06)."""

import shutil
import subprocess

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import AuditConfig
from vhecfsck.pipeline import run_audit
from vhecfsck.report import render_prometheus


def test_prometheus_renderer_structure() -> None:
    opened = open_scenario("tombstoned")
    try:
        report = run_audit(opened.adapter, AuditConfig())
    finally:
        opened.adapter.close()
    output = render_prometheus(report)

    assert "# HELP vhecfsck_up" in output
    assert "# TYPE vhecfsck_up gauge" in output
    assert 'vhecfsck_up{engine="synthetic"' in output
    assert "} 1\n" in output

    assert "vhecfsck_audit_verdict" in output
    assert "vhecfsck_canary_recall" in output
    assert "vhecfsck_dfi_ratio" in output
    assert "vhecfsck_hub_share_top1pct" in output
    assert "vhecfsck_antihub_fraction" in output
    assert "vhecfsck_partition_size_cv" in output
    assert "vhecfsck_vectors_live" in output
    assert "vhecfsck_vectors_deleted" in output


def test_prometheus_unavailable_metric_omits_gauge() -> None:
    opened = open_scenario("capability_limited")
    try:
        report = run_audit(opened.adapter, AuditConfig())
    finally:
        opened.adapter.close()
    output = render_prometheus(report)

    unavail_prefix = (
        'vhecfsck_metric_unavailable{engine="synthetic",'
        'index="capability_limited",metric="partition_size_cv"'
    )
    assert unavail_prefix in output
    unavail_suffix = (
        'metric="partition_size_cv",metric_space="L2",'
        'target="synthetic://capability_limited"} 1'
    )
    assert unavail_suffix in output
    assert 'vhecfsck_partition_size_cv{engine="synthetic"' not in output


def test_prometheus_promtool_check_if_installed() -> None:
    promtool = shutil.which("promtool")
    if not promtool:
        pytest.skip("promtool is not installed locally")

    opened = open_scenario("drifted")
    try:
        report = run_audit(opened.adapter, AuditConfig())
    finally:
        opened.adapter.close()
    output = render_prometheus(report)

    proc = subprocess.run(
        [promtool, "check", "metrics"],
        input=output,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"promtool check metrics failed: {proc.stderr}"
