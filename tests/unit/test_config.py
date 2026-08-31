"""P0-07: AuditConfig defaults, precedence, and validation (tests first)."""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from vhecfsck.config import (
    DEFAULT_THRESHOLDS,
    AuditConfig,
    Threshold,
    load_config,
)
from vhecfsck.errors import UsageError

# Spec table - 02-metrics-spec.md ss2-5. Keep in lockstep with DEFAULT_THRESHOLDS.
SPEC_THRESHOLDS: dict[str, tuple[float, float, str]] = {
    "canary_recall": (0.85, 0.70, "lower_is_worse"),
    "hub_share_top1pct": (0.20, 0.35, "higher_is_worse"),
    "antihub_fraction": (0.25, 0.40, "higher_is_worse"),
    "dfi": (0.15, 0.30, "higher_is_worse"),
    "partition_size_cv": (1.20, 2.00, "higher_is_worse"),
}


def test_default_thresholds_match_metrics_spec_table() -> None:
    for metric_id, (warn, fail, direction) in SPEC_THRESHOLDS.items():
        thr = DEFAULT_THRESHOLDS[metric_id]
        assert thr.warn == warn
        assert thr.fail == fail
        assert thr.direction == direction


def test_audit_config_defaults_are_frozen_and_typed() -> None:
    cfg = AuditConfig()
    assert cfg.seed == 1337
    assert cfg.queries == 200
    assert cfg.k == 10
    assert cfg.hubness_sample_size == 20_000
    assert cfg.k_hub == 10
    assert cfg.hubness_source == "truth"
    assert cfg.block_working_set_mb == 256
    assert cfg.strict_unavailable is False
    assert cfg.max_seconds is None
    assert cfg.max_memory_mb is None
    with pytest.raises(FrozenInstanceError):
        cfg.seed = 1  # type: ignore[misc]


def test_effective_config_is_serialisable() -> None:
    payload = AuditConfig().to_dict()
    assert payload["seed"] == 1337
    assert payload["thresholds"]["canary_recall"]["warn"] == 0.85
    assert payload["metrics_enabled"]["canary_recall"] is True


def test_precedence_config_file_over_defaults(tmp_path: Path) -> None:
    path = tmp_path / "vhecfsck.toml"
    path.write_text("[vhecfsck]\nseed = 42\n", encoding="utf-8")
    cfg = load_config(config_path=path)
    assert cfg.seed == 42
    assert cfg.k == 10


def test_precedence_env_over_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "vhecfsck.toml"
    path.write_text("[vhecfsck]\nseed = 42\n", encoding="utf-8")
    monkeypatch.setenv("VHECFSCK_SEED", "99")
    cfg = load_config(config_path=path, environ=os.environ)
    assert cfg.seed == 99


def test_precedence_cli_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "vhecfsck.toml"
    path.write_text("[vhecfsck]\nseed = 42\n", encoding="utf-8")
    monkeypatch.setenv("VHECFSCK_SEED", "99")
    cfg = load_config(config_path=path, environ=os.environ, cli_overrides={"seed": 7})
    assert cfg.seed == 7


def test_pyproject_tool_vhecfsck_section(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.vhecfsck]\nqueries = 50\n", encoding="utf-8")
    cfg = load_config(config_path=path)
    assert cfg.queries == 50


def test_unknown_key_raises_usage_error(tmp_path: Path) -> None:
    path = tmp_path / "vhecfsck.toml"
    path.write_text("[vhecfsck]\nnot_a_real_knob = 1\n", encoding="utf-8")
    with pytest.raises(UsageError) as excinfo:
        load_config(config_path=path)
    assert "not_a_real_knob" in str(excinfo.value)


def test_out_of_range_threshold_raises_usage_error() -> None:
    with pytest.raises(UsageError):
        Threshold(warn=0.50, fail=0.70, direction="lower_is_worse")
    with pytest.raises(UsageError):
        Threshold(warn=0.40, fail=0.20, direction="higher_is_worse")


def test_dimension_profiles_scale_with_dimension() -> None:
    from vhecfsck.config import (
        get_default_thresholds_for_dimension,
        get_profile_name_for_dimension,
        resolve_thresholds_for_dimension,
    )

    assert get_profile_name_for_dimension(16) == "low"
    assert get_profile_name_for_dimension(64) == "low"
    assert get_profile_name_for_dimension(128) == "medium"
    assert get_profile_name_for_dimension(384) == "medium"
    assert get_profile_name_for_dimension(768) == "high"
    assert get_profile_name_for_dimension(1536) == "ultra_high"

    low = get_default_thresholds_for_dimension(64)
    ultra = get_default_thresholds_for_dimension(1536)

    assert low["hub_share_top1pct"].warn == 0.20
    assert ultra["hub_share_top1pct"].warn == 0.35
    assert ultra["antihub_fraction"].warn == 0.46
    assert ultra["partition_size_cv"].warn == 1.50

    # User explicit override must be preserved over dimension calibration
    cfg = AuditConfig()
    cfg_override = load_config(
        cli_overrides={
            "thresholds": {"hub_share_top1pct": {"warn": 0.18, "fail": 0.30}}
        }
    )

    resolved_default = resolve_thresholds_for_dimension(cfg, 1536)
    assert resolved_default["hub_share_top1pct"].warn == 0.35  # calibrated ultra_high

    resolved_override = resolve_thresholds_for_dimension(cfg_override, 1536)
    assert (
        resolved_override["hub_share_top1pct"].warn == 0.18
    )  # explicit override preserved
