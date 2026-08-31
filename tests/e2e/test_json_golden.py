"""E2E tests for JSON report rendering, schema drift prevention, and golden files.

Ticket: P3-02.
"""

import json
from pathlib import Path

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import AuditConfig
from vhecfsck.models.report import report_from_dict
from vhecfsck.pipeline import run_audit
from vhecfsck.report.json_report import generate_report_schema, render_json

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _PROJECT_ROOT / "schema" / "report-1.1.json"
_GOLDEN_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "golden"


def test_json_schema_drift() -> None:
    """Committed schema matches current generate_report_schema() model."""
    assert _SCHEMA_PATH.exists(), f"missing published schema file at {_SCHEMA_PATH}"
    committed_content = _SCHEMA_PATH.read_text(encoding="utf-8")

    current_schema = generate_report_schema()
    rendered_current = json.dumps(current_schema, indent=2, ensure_ascii=False) + "\n"

    assert committed_content == rendered_current, (
        "Report Pydantic model and committed schema/report-1.1.json have diverged! "
        "Update schema/report-1.1.json to match."
    )


@pytest.mark.parametrize("name", ["healthy", "drifted", "tombstoned", "tiny"])
def test_json_golden_matching(name: str) -> None:
    """Audit output JSON matches committed golden file byte-by-byte."""
    golden_file = _GOLDEN_DIR / f"report-{name}.json"
    assert golden_file.exists(), f"missing golden file: {golden_file}"
    golden_text = golden_file.read_text(encoding="utf-8")

    opened = open_scenario(name)
    try:
        config = AuditConfig(seed=1337, k=10, queries=20)
        report = run_audit(
            opened.adapter,
            config,
            search_params=opened.spec.default_search_params,
        )

        report_dict = json.loads(render_json(report))
        report_dict["run"]["started_at"] = "2026-08-30T10:00:00Z"
        report_dict["run"]["duration_seconds"] = 0.5
        report_dict["run"]["stage_timings"] = dict.fromkeys(
            report_dict["run"]["stage_timings"], 0.1
        )
        report_dict["counts"]["read_at"] = "2026-08-30T10:00:00Z"
        for m in report_dict["metrics"]:
            if (
                "detail" in m
                and isinstance(m["detail"], dict)
                and "read_at" in m["detail"]
            ):
                m["detail"]["read_at"] = "2026-08-30T10:00:00Z"

        frozen_report = report_from_dict(report_dict)
        rendered = render_json(frozen_report)

        err_msg = (
            f"JSON output for {name} diverged from golden fixture {golden_file.name}"
        )
        assert rendered == golden_text, err_msg
    finally:
        opened.adapter.close()


def test_render_json_formatting_rules() -> None:
    """render_json enforces unix line endings, trailing newline, key sorting."""
    name = "tiny"
    opened = open_scenario(name)
    try:
        report = run_audit(
            opened.adapter,
            AuditConfig(seed=1337, k=5, queries=10),
            search_params=opened.spec.default_search_params,
        )
        rendered = render_json(report)

        # Check line endings and single trailing newline
        assert "\r" not in rendered
        assert rendered.endswith("\n")
        assert not rendered.endswith("\n\n")

        # Check key sorting in JSON payload
        data = json.loads(rendered)
        top_keys = list(data.keys())
        assert top_keys == sorted(top_keys)

        # Check float rounding to 6 decimal places max
        def check_floats(obj: object) -> None:
            if isinstance(obj, float):
                formatted = f"{obj:.10f}".rstrip("0")
                if "." in formatted:
                    decimals = len(formatted.split(".")[1])
                    assert decimals <= 6, f"float {obj} has >6 decimal places"
            elif isinstance(obj, dict):
                for v in obj.values():
                    check_floats(v)
            elif isinstance(obj, list):
                for item in obj:
                    check_floats(item)

        check_floats(data)
    finally:
        opened.adapter.close()
