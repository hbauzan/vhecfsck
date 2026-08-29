"""P0-05: error taxonomy and exit-code contract (tests first)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from vhecfsck.errors import (
    CapabilityError,
    ExitCode,
    InconclusiveError,
    InternalError,
    TargetConnectionError,
    UsageError,
    VhecfsckError,
    handle_uncaught,
)

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "vhecfsck"

# Frozen stable machine codes — a new subclass without an entry fails the suite.
FROZEN_CODES = (
    "usage",
    "target_connection",
    "capability",
    "inconclusive",
    "internal",
)

SUBCLASS_TABLE: list[tuple[type[VhecfsckError], ExitCode, str]] = [
    (UsageError, ExitCode.USAGE, "usage"),
    (TargetConnectionError, ExitCode.USAGE, "target_connection"),
    (CapabilityError, ExitCode.INCONCLUSIVE, "capability"),
    (InconclusiveError, ExitCode.INCONCLUSIVE, "inconclusive"),
    (InternalError, ExitCode.INTERNAL, "internal"),
]


def test_exit_code_values_match_metrics_spec_section_6() -> None:
    assert ExitCode.OK == 0
    assert ExitCode.WARN == 1
    assert ExitCode.FAIL == 2
    assert ExitCode.INCONCLUSIVE == 3
    assert ExitCode.USAGE == 4
    assert ExitCode.INTERNAL == 70


@pytest.mark.parametrize(("cls", "exit_code", "code"), SUBCLASS_TABLE)
def test_subclass_maps_to_documented_exit_and_code(
    cls: type[VhecfsckError],
    exit_code: ExitCode,
    code: str,
) -> None:
    err = cls("boom", hint="try again")
    assert err.exit_code == exit_code
    assert err.code == code
    assert err.hint == "try again"
    assert isinstance(err, VhecfsckError)


def test_code_strings_are_unique_and_frozen() -> None:
    codes = [row[2] for row in SUBCLASS_TABLE]
    assert codes == list(FROZEN_CODES)
    assert len(set(codes)) == len(codes)


def test_handle_uncaught_maps_unknown_to_internal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        raise RuntimeError("surprise")
    except RuntimeError as exc:
        code = handle_uncaught(exc, debug=False)
    assert code == ExitCode.INTERNAL
    err = capsys.readouterr().err
    assert "internal" in err.lower() or "Internal" in err
    assert "--debug" in err
    assert "Traceback" not in err


def test_handle_uncaught_debug_shows_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        raise RuntimeError("surprise")
    except RuntimeError as exc:
        code = handle_uncaught(exc, debug=True)
    assert code == ExitCode.INTERNAL
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "surprise" in err


def test_handle_uncaught_preserves_vhecfsck_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = handle_uncaught(UsageError("bad flag", hint="see --help"), debug=False)
    assert code == ExitCode.USAGE
    err = capsys.readouterr().err
    assert "bad flag" in err
    assert "see --help" in err


def test_no_bare_exception_or_systemexit_outside_errors() -> None:
    """Acceptance: no bare raise Exception / SystemExit outside errors.py."""
    banned: list[str] = []
    for path in PKG.rglob("*.py"):
        if path.name == "errors.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc
            name: str | None = None
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            if name in {"Exception", "SystemExit", "BaseException"}:
                banned.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
    assert not banned, "bare raises outside errors.py:\n" + "\n".join(banned)
