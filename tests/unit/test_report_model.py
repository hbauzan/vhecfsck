"""Unit tests for P3-01 report schema (Pydantic v2 validation, round-trip, diff)."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from vhecfsck.models.corpus import IndexCounts
from vhecfsck.models.metrics import (
    Direction,
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
    Verdict,
)
from vhecfsck.models.report import (
    SCHEMA_VERSION,
    Report,
    RunContext,
    report_from_dict,
    report_to_dict,
)
from vhecfsck.models.target import IndexKind, MetricSpace, TargetDescriptor


def _sample_report() -> Report:
    run = RunContext(
        started_at="2026-08-30T10:00:00Z",
        duration_seconds=12.5,
        seed=1337,
        deterministic=True,
        stage_timings={"gt": 2.1, "canary": 5.4},
        host={"cpu_count": 8, "blas": "accelerate"},
    )
    target = TargetDescriptor(
        engine="synthetic",
        engine_version="0.1.0",
        index_kind=IndexKind.IVF_PQ,
        index_name="test_index",
        location="synthetic://healthy",
        dimension=128,
        metric_space=MetricSpace.COSINE,
    )
    counts = IndexCounts(
        live=1000,
        deleted=10,
        total=1010,
        indexed=1000,
        degenerate=0,
        exact=True,
        read_at=datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC),
    )
    metric = MetricResult(
        id="canary_recall",
        state=MetricState.OK,
        value=0.98,
        unit="ratio",
        thresholds=ThresholdSpec(
            warn=0.90,
            fail=0.80,
            direction=Direction.LOWER_IS_WORSE,
        ),
        sampling={"queries": 100, "k": 10},
        detail={"recall_id": 0.98},
        evidence_strength=EvidenceStrength.HIGH,
        explanation="Recall is healthy",
        remediation_hint="",
    )
    return Report(
        schema_version=SCHEMA_VERSION,
        tool_version="0.1.0",
        verdict=Verdict.OK,
        run=run,
        target=target,
        counts=counts,
        metrics=(metric,),
        warnings=("all good",),
        config={"k": 10},
        degenerate=0,
        offending_vector_ids=(),
    )


def test_schema_version_constant() -> None:
    """schema_version matches recorded constant (1.0)."""
    assert SCHEMA_VERSION == "1.0"
    report = _sample_report()
    assert report.schema_version == "1.0"


def test_report_round_trip() -> None:
    """Report → dict → Report and Report → JSON → Report round-trips losslessly."""
    report = _sample_report()
    as_dict = report_to_dict(report)
    deserialized = report_from_dict(as_dict)
    assert deserialized == report

    json_str = json.dumps(as_dict)
    reloaded = report_from_dict(json.loads(json_str))
    assert reloaded == report


def test_extra_fields_forbidden() -> None:
    """Passing extra unknown fields to RunContext or report_from_dict raises error."""
    with pytest.raises(ValidationError):
        RunContext(
            started_at="2026-08-30T10:00:00Z",
            duration_seconds=1.0,
            seed=42,
            deterministic=True,
            stage_timings={},
            host={},
            unexpected_field="invalid",
        )

    base_dict = report_to_dict(_sample_report())
    base_dict["unknown_top_field"] = "bad"
    with pytest.raises(ValueError, match="Unknown top-level field"):
        report_from_dict(base_dict)


def test_secret_leak_prevention() -> None:
    """Creating a Report containing credentials or secret tokens raises ValueError."""
    base_report = _sample_report()

    with pytest.raises(ValueError, match="credential"):
        Report(
            schema_version=base_report.schema_version,
            tool_version=base_report.tool_version,
            verdict=base_report.verdict,
            run=base_report.run,
            target=base_report.target,
            counts=base_report.counts,
            metrics=base_report.metrics,
            warnings=("secret leaking: sk-proj-SECRETKEY123456789012345",),
            config=base_report.config,
        )

    with pytest.raises(ValueError, match="credential"):
        Report(
            schema_version=base_report.schema_version,
            tool_version=base_report.tool_version,
            verdict=base_report.verdict,
            run=base_report.run,
            target=TargetDescriptor(
                engine="pgvector",
                engine_version="16",
                index_kind=IndexKind.HNSW,
                index_name="items",
                location="postgres://alice:s3cret@db.example:5432/vectors",
                dimension=4,
                metric_space=MetricSpace.L2,
            ),
            counts=base_report.counts,
            metrics=base_report.metrics,
            warnings=base_report.warnings,
            config=base_report.config,
        )


def test_redacted_engine_location_is_not_treated_as_a_leak() -> None:
    """P7 adapters put redacted DSNs in ``location``; that is not a leak."""
    from vhecfsck.logging import redact_secrets

    base = _sample_report()
    location = redact_secrets(
        "postgres://alice:s3cret@db.example:5432/vectors?table=t&column=v"
    )
    assert "s3cret" not in location
    report = Report(
        schema_version=base.schema_version,
        tool_version=base.tool_version,
        verdict=base.verdict,
        run=base.run,
        target=TargetDescriptor(
            engine="pgvector",
            engine_version="16",
            index_kind=IndexKind.HNSW,
            index_name="items",
            location=location,
            dimension=4,
            metric_space=MetricSpace.L2,
        ),
        counts=base.counts,
        metrics=base.metrics,
        warnings=base.warnings,
        config=base.config,
    )
    assert "s3cret" not in str(report.model_dump_dict())
    assert "REDACTED" in report.target.location


def test_report_compare() -> None:
    """Report.compare produces structured delta for baseline comparison."""
    rep1 = _sample_report()

    # Create second report with changed verdict, counts, and metrics
    rep2_dict = report_to_dict(rep1)
    rep2_dict["verdict"] = "FAIL"
    rep2_dict["counts"]["live"] = 1200
    rep2_dict["counts"]["deleted"] = 50
    rep2_dict["metrics"][0]["value"] = 0.75
    rep2_dict["metrics"][0]["state"] = "FAIL"
    rep2_dict["warnings"].append("degradation detected")

    rep2 = report_from_dict(rep2_dict)

    diff = rep1.compare(rep2)
    assert diff["same_schema"] is True
    assert diff["verdict_changed"] is True
    assert diff["verdict_delta"] == {"from": "OK", "to": "FAIL"}
    assert diff["counts_delta"]["live"] == 200
    assert diff["counts_delta"]["deleted"] == 40
    assert diff["metrics_delta"]["canary_recall"]["state_from"] == "OK"
    assert diff["metrics_delta"]["canary_recall"]["state_to"] == "FAIL"
    assert pytest.approx(diff["metrics_delta"]["canary_recall"]["delta"]) == -0.23
    assert diff["warnings_diff"]["added"] == ["degradation detected"]
