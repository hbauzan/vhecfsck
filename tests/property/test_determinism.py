"""P2-11: Determinism harness tests.

Verifies that running audit reports across in-process and subprocess executions
with identical fixed seeds yields byte-identical serialized output after
normalising a frozen allowlist of volatile runtime fields.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import AuditConfig
from vhecfsck.models.report import report_to_dict
from vhecfsck.pipeline import run_audit
from vhecfsck.synthetic.scenarios import SCENARIO_NAMES

# Frozen allowlist of volatile fields that vary across executions
# (timestamps, durations, host environment).
FROZEN_VOLATILE_ALLOWLIST: tuple[str, ...] = (
    "run.started_at",
    "run.duration_seconds",
    "run.stage_timings",
    "run.host",
    "counts.read_at",
)


def _strip_volatile_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively copy and normalize volatile fields in report dict."""
    out = json.loads(json.dumps(d))

    if "run" in out and isinstance(out["run"], dict):
        out["run"]["started_at"] = "<VOLATILE>"
        out["run"]["duration_seconds"] = 0.0
        out["run"]["stage_timings"] = {"<VOLATILE>": 0.0}
        out["run"]["host"] = {"<VOLATILE>": "<VOLATILE>"}

    if "counts" in out and isinstance(out["counts"], dict):
        out["counts"]["read_at"] = "<VOLATILE>"

    return out


def test_volatile_allowlist_is_frozen() -> None:
    """Ensure the volatile-field allowlist cannot be silently modified."""
    expected = (
        "run.started_at",
        "run.duration_seconds",
        "run.stage_timings",
        "run.host",
        "counts.read_at",
    )
    assert expected == FROZEN_VOLATILE_ALLOWLIST


@pytest.mark.parametrize("scenario_name", SCENARIO_NAMES)
def test_scenario_audit_is_deterministic_in_process(scenario_name: str) -> None:
    """Run audit twice in-process and assert normalized report dicts match exactly."""
    config = AuditConfig(seed=42)

    opened1 = open_scenario(scenario_name, size="tiny")
    report1 = run_audit(opened1.adapter, config)
    opened1.adapter.close()

    opened2 = open_scenario(scenario_name, size="tiny")
    report2 = run_audit(opened2.adapter, config)
    opened2.adapter.close()

    dict1 = _strip_volatile_fields(report_to_dict(report1))
    dict2 = _strip_volatile_fields(report_to_dict(report2))

    assert json.dumps(dict1, sort_keys=True) == json.dumps(dict2, sort_keys=True)


def test_scenario_audit_is_deterministic_cross_process_and_hash_seed() -> None:
    """Run audit in sub-process with varied hash seed; verify byte-identical output."""
    scenario_name = "healthy"
    code = f"""
import json
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import AuditConfig
from vhecfsck.models.report import report_to_dict
from vhecfsck.pipeline import run_audit
from tests.property.test_determinism import _strip_volatile_fields

opened = open_scenario("{scenario_name}", size="tiny")
report = run_audit(opened.adapter, AuditConfig(seed=123))
opened.adapter.close()
norm = _strip_volatile_fields(report_to_dict(report))
print(json.dumps(norm, sort_keys=True))
"""
    env1 = {**os.environ, "PYTHONHASHSEED": "0"}
    env2 = {**os.environ, "PYTHONHASHSEED": "42"}

    proc1 = subprocess.run(
        [sys.executable, "-c", code],
        env=env1,
        capture_output=True,
        text=True,
        check=True,
    )
    proc2 = subprocess.run(
        [sys.executable, "-c", code],
        env=env2,
        capture_output=True,
        text=True,
        check=True,
    )

    assert proc1.stdout.strip() == proc2.stdout.strip()
