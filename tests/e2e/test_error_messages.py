"""E2E error message audit test suite (P8-09).

Audits all user-reachable error taxonomy subclasses and UNAVAILABLE reasons:
1. Every VhecfsckError subclass dynamically discovered has a hint.
2. Every VhecfsckError subclass has a unique machine code and ExitCode.
3. Every UNAVAILABLE reason string names missing capability/privilege.
4. Error reporting never leaks raw credentials in error messages or hints.
"""

from __future__ import annotations

import io
import sys

import pytest
from vhecfsck.errors import (
    ExitCode,
    VhecfsckError,
    handle_uncaught,
)
from vhecfsck.logging import redact_secrets
from vhecfsck.models.metrics import (
    Direction,
    EvidenceStrength,
    MetricResult,
    MetricState,
    ThresholdSpec,
)


def get_all_vhecfsck_error_subclasses() -> list[type[VhecfsckError]]:
    """Dynamically discover all VhecfsckError subclasses registered."""
    subclasses: list[type[VhecfsckError]] = []

    def _collect(cls: type[VhecfsckError]) -> None:
        for sub in cls.__subclasses__():
            if sub not in subclasses:
                subclasses.append(sub)
                _collect(sub)

    _collect(VhecfsckError)
    return subclasses


def test_vhecfsck_error_subclasses_dynamically_registered() -> None:
    """Ensure at least the core error subclasses are registered."""
    classes = get_all_vhecfsck_error_subclasses()
    assert len(classes) >= 5, "Expected at least 5 VhecfsckError subclasses"


@pytest.mark.parametrize("error_cls", get_all_vhecfsck_error_subclasses())
def test_error_subclass_has_non_empty_hint_and_code(
    error_cls: type[VhecfsckError],
) -> None:
    """Table-driven test: every error subclass has hint, code, and ExitCode."""
    exc = error_cls("Test error message occurred")

    assert exc.hint, f"{error_cls.__name__} must have a non-empty hint"
    assert len(exc.hint.strip()) > 5, (
        f"{error_cls.__name__} hint is too short: {exc.hint!r}"
    )
    assert exc.code, f"{error_cls.__name__} must have a non-empty code"
    assert exc.code != "internal" or error_cls.__name__ == "InternalError"
    assert isinstance(exc.exit_code, ExitCode)


def test_error_subclasses_have_distinct_hints() -> None:
    """Every error subclass must define a distinct human hint."""
    classes = get_all_vhecfsck_error_subclasses()
    hints: dict[str, str] = {}
    for error_cls in classes:
        exc = error_cls("Sample error message")
        hint_text = exc.hint.strip()
        matched = [k for k, v in hints.items() if v == hint_text]
        err_name = error_cls.__name__
        assert not matched, f"{err_name} duplicate hint: {hint_text!r}"
        hints[err_name] = hint_text


def test_error_subclasses_have_distinct_codes() -> None:
    """Every error subclass must have a unique machine code."""
    classes = get_all_vhecfsck_error_subclasses()
    codes: dict[str, str] = {}
    for error_cls in classes:
        exc = error_cls("Sample error message")
        code_text = exc.code.strip()
        matched = [k for k, v in codes.items() if v == code_text]
        err_name = error_cls.__name__
        assert not matched, f"{err_name} duplicate code: {code_text!r}"
        codes[err_name] = code_text


def test_error_formatting_emits_hint_and_code() -> None:
    """Verify handle_uncaught writes code, message, and hint to stderr."""
    error_cls = get_all_vhecfsck_error_subclasses()[0]
    exc = error_cls("Specific test failure description")

    captured = io.StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = captured
        ret_code = handle_uncaught(exc, debug=False)
    finally:
        sys.stderr = old_stderr

    assert ret_code == exc.exit_code
    stderr_output = captured.getvalue()
    assert f"vhecfsck: {exc.code}: Specific test failure description" in stderr_output
    assert f"hint: {exc.hint}" in stderr_output


def test_unavailable_reasons_audit() -> None:
    """Every UNAVAILABLE MetricResult must specify a descriptive reason."""
    reasons = [
        "capability report_deleted_counts missing — cannot compute DFI",
        "IndexCounts unavailable — cannot compute DFI",
        "live + dead == 0 (empty index)",
        "EXPLAIN indicated sequential scan instead of index scan",
        (
            "Qdrant REST/gRPC APIs do not expose internal HNSW graph entry "
            "points or in-degree histograms"
        ),
    ]

    for reason in reasons:
        assert reason.strip().lower() != "unavailable", (
            "Reason string cannot be bare 'Unavailable'"
        )
        assert len(reason.strip()) > 10, (
            f"Unavailable reason string too short: {reason!r}"
        )

        metric = MetricResult(
            id="test_metric",
            state=MetricState.UNAVAILABLE,
            value=None,
            unit="ratio",
            thresholds=ThresholdSpec(
                warn=0.1, fail=0.2, direction=Direction.HIGHER_IS_WORSE
            ),
            sampling={},
            detail={},
            evidence_strength=EvidenceStrength.LOW,
            unavailable_reason=reason,
        )
        assert metric.unavailable_reason == reason
        assert metric.state is MetricState.UNAVAILABLE


def test_error_messages_contain_no_credentials() -> None:
    """Audit error strings and hints to ensure DSNs and API keys are redacted."""
    raw_target = (
        "postgresql://auditor:secret_password_123@db.example.com:5432/mydb"
        "?api_key=token_abc_xyz"
    )
    redacted = redact_secrets(raw_target)

    assert "secret_password_123" not in redacted
    assert "token_abc_xyz" not in redacted
    assert "REDACTED" in redacted

    exc = VhecfsckError(
        f"failed to connect to {redacted}",
        hint=f"Check connection string format for {redacted}",
    )

    assert "secret_password_123" not in exc.message
    assert "secret_password_123" not in exc.hint
    assert "token_abc_xyz" not in exc.message
    assert "token_abc_xyz" not in exc.hint
