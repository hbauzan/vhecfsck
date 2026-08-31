"""Unit tests for baseline mode, comparability, and delta gating (P8-03)."""

from __future__ import annotations

import pytest
from vhecfsck.adapters.scenarios import open_scenario
from vhecfsck.config import load_config
from vhecfsck.core.baseline import (
    GateMode,
    NotComparableError,
    check_comparability,
    evaluate_baseline_delta,
)
from vhecfsck.errors import ExitCode
from vhecfsck.models import Verdict
from vhecfsck.pipeline import run_audit


def test_baseline_unchanged_index_yields_ok_deltas() -> None:
    """Two audits of an unchanged index yield OK deltas within noise."""
    opened = open_scenario("healthy", size="small")
    try:
        cfg = load_config(cli_overrides={"seed": 42})
        report1 = run_audit(opened.adapter, cfg)
        report2 = run_audit(opened.adapter, cfg)

        diff, verdict = evaluate_baseline_delta(
            report1, report2, cfg, gate_mode=GateMode.BOTH
        )
        assert verdict == Verdict.OK
        assert diff["comparable"] is True
        for _m_id, m_diff in diff["metrics_delta"].items():
            assert m_diff["delta_state"] in ("OK", "UNAVAILABLE", "DISABLED")
    finally:
        opened.adapter.close()


def test_baseline_churn_triggers_delta_gate() -> None:
    """Audit after degradation triggers delta gate even if absolute threshold is met."""
    opened_healthy = open_scenario("healthy", size="small")
    opened_drifted = open_scenario("drifted", size="small")
    try:
        cfg = load_config(cli_overrides={"seed": 42})
        base_report = run_audit(opened_healthy.adapter, cfg)
        curr_report = run_audit(opened_drifted.adapter, cfg)

        # Evaluate with delta gate mode
        _diff, verdict = evaluate_baseline_delta(
            base_report, curr_report, cfg, gate_mode=GateMode.DELTA
        )
        # Drifted scenario recall drops significantly, so delta verdict is WARN/FAIL
        assert verdict in (Verdict.WARN, Verdict.FAIL)
    finally:
        opened_healthy.adapter.close()
        opened_drifted.adapter.close()


@pytest.mark.parametrize(
    "param_override, expected_field",
    [
        ({"seed": 999}, "seed"),
        ({"k": 20}, "k"),
        ({"hubness_sample_size": 1000}, "hubness_sample_size"),
        ({"k_hub": 5}, "k_hub"),
    ],
)
def test_baseline_mismatched_parameters_raises_not_comparable(
    param_override: dict[str, int], expected_field: str
) -> None:
    """Any mismatch in comparability parameters raises NotComparableError (exit 3)."""
    opened = open_scenario("healthy", size="tiny")
    try:
        cfg1 = load_config(
            cli_overrides={
                "seed": 42,
                "k": 10,
                "hubness_sample_size": 2000,
                "k_hub": 10,
            }
        )
        cfg2 = load_config(
            cli_overrides={
                "seed": 42,
                "k": 10,
                "hubness_sample_size": 2000,
                "k_hub": 10,
                **param_override,
            }
        )

        rep1 = run_audit(opened.adapter, cfg1)
        rep2 = run_audit(opened.adapter, cfg2)

        with pytest.raises(NotComparableError) as exc_info:
            check_comparability(rep1, rep2)

        assert exc_info.value.exit_code == ExitCode.INCONCLUSIVE
        assert exc_info.value.code == "not_comparable"
        assert expected_field in str(exc_info.value)
    finally:
        opened.adapter.close()
