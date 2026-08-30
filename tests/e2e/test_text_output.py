"""E2E tests for rich terminal report rendering (P3-03).

Verifies text presentation, ANSI color toggle, verdict banners, metric tables,
UNAVAILABLE visual distinction, offending vector details, and warnings.
"""

from __future__ import annotations

import re

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import AuditConfig
from vhecfsck.models.metrics import MetricState
from vhecfsck.pipeline import run_audit
from vhecfsck.report.text_report import render_terminal

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mG]")


@pytest.mark.parametrize(
    "name", ["healthy", "drifted", "tombstoned", "hubby", "capability_limited", "tiny"]
)
def test_render_terminal_all_scenarios_smoke(name: str) -> None:
    """render_terminal executes cleanly for all standard synthetic scenarios."""
    opened = open_scenario(name)
    try:
        config = AuditConfig(seed=1337, k=5, queries=10)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )

        plain_text = render_terminal(report, color=False)
        color_text = render_terminal(report, color=True)

        assert isinstance(plain_text, str)
        assert len(plain_text) > 0
        assert isinstance(color_text, str)
        assert len(color_text) > 0
    finally:
        opened.adapter.close()


def test_render_terminal_no_ansi_when_color_false() -> None:
    """When color=False, strictly zero ANSI escape sequences are emitted."""
    opened = open_scenario("tombstoned")
    try:
        config = AuditConfig(seed=1337, k=5, queries=10)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )
        rendered = render_terminal(report, color=False)

        assert "\x1b" not in rendered
        assert _ANSI_ESCAPE_RE.search(rendered) is None

        # Verify key sections exist in plain text
        assert "AUDIT TARGET IDENTITY" in rendered
        assert "AUDIT VERDICT:" in rendered
        assert "Index Cardinality" in rendered
        assert "Audit Metrics" in rendered
    finally:
        opened.adapter.close()


def test_render_terminal_ansi_when_color_true() -> None:
    """When color=True, ANSI escape sequences are included for styling."""
    opened = open_scenario("healthy")
    try:
        config = AuditConfig(seed=1337, k=5, queries=10)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )
        rendered = render_terminal(report, color=True)

        assert "\x1b[" in rendered
        assert "\x1b[0m" in rendered
    finally:
        opened.adapter.close()


def test_render_terminal_verdict_banners() -> None:
    """Verdict banner matches overall report verdict and uses distinct color styling."""
    for scenario_name in ["healthy", "tombstoned", "hubby"]:
        opened = open_scenario(scenario_name)
        try:
            config = AuditConfig(seed=1337, k=5, queries=10)
            report = run_audit(
                opened.adapter,
                config,
                search_params=opened.spec.default_search_params,
            )

            plain = render_terminal(report, color=False)
            colored = render_terminal(report, color=True)

            assert f"AUDIT VERDICT: {report.verdict.value}" in plain
            assert f"AUDIT VERDICT: {report.verdict.value}" in colored
            assert "\x1b[" in colored
        finally:
            opened.adapter.close()


def test_render_terminal_unavailable_distinct_from_ok() -> None:
    """UNAVAILABLE metric state is rendered with visual distinction and reason."""
    opened = open_scenario("capability_limited")
    try:
        config = AuditConfig(seed=1337, k=5, queries=10)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )

        # Confirm there is an UNAVAILABLE metric in this report
        has_unavail = any(m.state is MetricState.UNAVAILABLE for m in report.metrics)
        msg = "expected capability_limited scenario to have UNAVAILABLE metric"
        assert has_unavail, msg

        plain = render_terminal(report, color=False)
        colored = render_terminal(report, color=True)

        # UNAVAILABLE badge and reason presence
        assert "UNAVAILABLE" in plain
        assert "Reason      :" in plain

        # Cyan ANSI code (\x1b[36m) for UNAVAILABLE is distinct from Green (\x1b[32m)
        assert "\x1b[36m" in colored
        assert "\x1b[32m" in colored
    finally:
        opened.adapter.close()


def test_render_terminal_offending_vectors_and_warnings() -> None:
    """Offending vector IDs and report warnings are rendered in dedicated sections."""
    opened = open_scenario("tombstoned")
    try:
        config = AuditConfig(seed=1337, k=5, queries=10)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )

        # Inject offending vector IDs and warnings into report copy for test
        report_with_extras = report.model_copy(
            update={
                "offending_vector_ids": (42, 107, 889),
                "warnings": ("Custom tombstone warning test",),
            }
        )

        rendered = render_terminal(report_with_extras, color=False)

        assert "--- Offending Vectors ---" in rendered
        assert "Count : 3" in rendered
        assert "[42, 107, 889]" in rendered
        assert "--- Warnings ---" in rendered
        assert "! Custom tombstone warning test" in rendered
    finally:
        opened.adapter.close()
