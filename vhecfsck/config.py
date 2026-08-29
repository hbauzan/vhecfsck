"""Audit configuration, threshold defaults, and layered overrides.

Default thresholds are inherited from ``roadmap/02-metrics-spec.md`` (not yet
independently calibrated - see ADR-0011). A table-driven test locks the values
so code and spec cannot drift.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from vhecfsck.errors import UsageError

Direction = Literal["lower_is_worse", "higher_is_worse"]
HubnessSource = Literal["truth", "engine"]

# Defaults cited from roadmap/02-metrics-spec.md ss2-5 (ADR-0011 provenance).
_SPEC_THRESHOLD_TABLE: dict[str, tuple[float, float, Direction]] = {
    "canary_recall": (0.85, 0.70, "lower_is_worse"),
    "hub_share_top1pct": (0.20, 0.35, "higher_is_worse"),
    "antihub_fraction": (0.25, 0.40, "higher_is_worse"),
    "dfi": (0.15, 0.30, "higher_is_worse"),
    "partition_size_cv": (1.20, 2.00, "higher_is_worse"),
}

_METRIC_IDS: tuple[str, ...] = tuple(_SPEC_THRESHOLD_TABLE)


@dataclass(frozen=True)
class Threshold:
    """Warn/fail pair for one metric, with gating direction."""

    warn: float
    fail: float
    direction: Direction

    def __post_init__(self) -> None:
        if self.direction == "lower_is_worse":
            if not (self.warn > self.fail):
                raise UsageError(
                    "lower_is_worse requires warn > fail "
                    f"(got warn={self.warn}, fail={self.fail})",
                    hint="For recall-like metrics, warn is the higher bound.",
                )
        elif self.direction == "higher_is_worse":
            if not (self.warn < self.fail):
                raise UsageError(
                    "higher_is_worse requires warn < fail "
                    f"(got warn={self.warn}, fail={self.fail})",
                    hint="For DFI/hubness-like metrics, warn is the lower bound.",
                )
        else:
            raise UsageError(
                f"unknown threshold direction: {self.direction!r}",
                hint="Use lower_is_worse or higher_is_worse.",
            )

    def to_dict(self) -> dict[str, float | str]:
        """JSON-friendly representation for report embedding."""
        return {"warn": self.warn, "fail": self.fail, "direction": self.direction}


def _default_thresholds() -> dict[str, Threshold]:
    return {
        metric_id: Threshold(warn=warn, fail=fail, direction=direction)
        for metric_id, (warn, fail, direction) in _SPEC_THRESHOLD_TABLE.items()
    }


DEFAULT_THRESHOLDS: Mapping[str, Threshold] = _default_thresholds()


def _default_metrics_enabled() -> dict[str, bool]:
    return dict.fromkeys(_METRIC_IDS, True)


@dataclass(frozen=True)
class AuditConfig:
    """Fully-resolved, immutable audit configuration.

    Precedence when loading: built-in defaults → config file → ``VHECFSCK_*``
    env vars → CLI overrides.
    """

    seed: int = 1337  # metrics-spec §1
    queries: int = 200  # metrics-spec canary sampling example
    k: int = 10
    hubness_sample_size: int = 20_000  # metrics-spec §3 / ADR-0006
    k_hub: int = 10
    hubness_source: HubnessSource = "truth"
    max_seconds: float | None = None  # no wall-clock cap until CLI sets one
    max_memory_mb: float | None = None  # no memory cap until CLI sets one
    block_working_set_mb: int = 256  # architecture §5 (~256 MB blocks)
    strict_unavailable: bool = False
    metrics_enabled: Mapping[str, bool] = field(
        default_factory=_default_metrics_enabled
    )
    thresholds: Mapping[str, Threshold] = field(default_factory=_default_thresholds)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the effective config for embedding in the report."""
        data = asdict(self)
        data["thresholds"] = {
            key: value.to_dict() if isinstance(value, Threshold) else value
            for key, value in self.thresholds.items()
        }
        data["metrics_enabled"] = dict(self.metrics_enabled)
        return data


_SCALAR_KEYS = frozenset(
    {
        "seed",
        "queries",
        "k",
        "hubness_sample_size",
        "k_hub",
        "hubness_source",
        "max_seconds",
        "max_memory_mb",
        "block_working_set_mb",
        "strict_unavailable",
    }
)


def load_config(
    *,
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> AuditConfig:
    """Resolve ``AuditConfig`` applying the documented precedence stack."""
    cfg = AuditConfig()
    if config_path is not None:
        cfg = _apply_mapping(
            cfg, _load_file_mapping(config_path), source=str(config_path)
        )
    if environ is not None:
        cfg = _apply_mapping(cfg, _env_mapping(environ), source="environment")
    if cli_overrides:
        cfg = _apply_mapping(cfg, dict(cli_overrides), source="cli")
    return cfg


def _load_file_mapping(path: Path) -> dict[str, Any]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if path.name == "pyproject.toml":
        tool = raw.get("tool", {})
        if not isinstance(tool, dict):
            raise UsageError(
                "pyproject.toml [tool] must be a table",
                hint="Use [tool.vhecfsck] for overrides.",
            )
        section = tool.get("vhecfsck", {})
    else:
        section = raw.get("vhecfsck", raw.get("tool", {}).get("vhecfsck", raw))
    if not isinstance(section, dict):
        raise UsageError(
            f"config section in {path} must be a table",
            hint="Use [vhecfsck] or [tool.vhecfsck].",
        )
    return section


def _env_mapping(environ: Mapping[str, str]) -> dict[str, Any]:
    prefix = "VHECFSCK_"
    out: dict[str, Any] = {}
    for key, value in environ.items():
        if not key.startswith(prefix):
            continue
        field_name = key[len(prefix) :].lower()
        out[field_name] = _parse_env_value(field_name, value)
    return out


def _parse_env_value(field_name: str, value: str) -> Any:
    if field_name == "strict_unavailable":
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if field_name in {
        "seed",
        "queries",
        "k",
        "hubness_sample_size",
        "k_hub",
        "block_working_set_mb",
    }:
        return int(value)
    if field_name in {"max_seconds", "max_memory_mb"}:
        return float(value)
    return value


def _apply_mapping(
    cfg: AuditConfig, updates: Mapping[str, Any], *, source: str
) -> AuditConfig:
    kwargs: dict[str, Any] = {}
    thresholds = dict(cfg.thresholds)
    metrics_enabled = dict(cfg.metrics_enabled)

    for key, value in updates.items():
        if key == "thresholds":
            if not isinstance(value, dict):
                raise UsageError(
                    f"thresholds in {source} must be a table",
                    hint="Example: [vhecfsck.thresholds.canary_recall]",
                )
            thresholds = _merge_thresholds(thresholds, value, source=source)
            continue
        if key in {"metrics_enabled", "metrics"}:
            if not isinstance(value, dict):
                raise UsageError(
                    f"metrics_enabled in {source} must be a table",
                    hint="Use metric id keys with boolean values.",
                )
            for metric_id, enabled in value.items():
                if metric_id not in metrics_enabled:
                    raise UsageError(
                        f"unknown metric {metric_id!r} in {source}",
                        hint=f"Known metrics: {', '.join(_METRIC_IDS)}",
                    )
                metrics_enabled[metric_id] = bool(enabled)
            continue
        if key not in _SCALAR_KEYS:
            raise UsageError(
                f"unknown config key {key!r} from {source}",
                hint=(
                    "Unknown keys are rejected so typos cannot silently disable checks."
                ),
            )
        kwargs[key] = value

    if thresholds != cfg.thresholds:
        kwargs["thresholds"] = thresholds
    if metrics_enabled != cfg.metrics_enabled:
        kwargs["metrics_enabled"] = metrics_enabled
    return replace(cfg, **kwargs) if kwargs else cfg


def _merge_thresholds(
    base: dict[str, Threshold],
    updates: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, Threshold]:
    merged = dict(base)
    for metric_id, raw in updates.items():
        if metric_id not in merged:
            raise UsageError(
                f"unknown threshold metric {metric_id!r} in {source}",
                hint=f"Known metrics: {', '.join(_METRIC_IDS)}",
            )
        if not isinstance(raw, dict):
            raise UsageError(
                f"threshold {metric_id!r} in {source} must be a table",
                hint="Provide warn, fail, and optionally direction.",
            )
        current = merged[metric_id]
        warn = float(raw.get("warn", current.warn))
        fail = float(raw.get("fail", current.fail))
        direction = raw.get("direction", current.direction)
        unknown = set(raw) - {"warn", "fail", "direction"}
        if unknown:
            raise UsageError(
                f"unknown threshold fields {sorted(unknown)} "
                f"on {metric_id} in {source}",
                hint="Only warn, fail, and direction are allowed.",
            )
        merged[metric_id] = Threshold(warn=warn, fail=fail, direction=direction)
    return merged
