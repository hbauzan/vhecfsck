"""Central error taxonomy and process exit codes.

Implements ADR-0004 and roadmap/02-metrics-spec.md §6. All failure modes that
reach the process boundary must map through this module — never via a bare
``raise Exception`` or ``SystemExit`` elsewhere in the package.
"""

from __future__ import annotations

import sys
import traceback
from enum import IntEnum
from typing import Final


class ExitCode(IntEnum):
    """Process exit codes — values locked to metrics-spec §6 / ADR-0004."""

    OK = 0
    WARN = 1
    FAIL = 2
    INCONCLUSIVE = 3
    USAGE = 4
    INTERNAL = 70


class VhecfsckError(Exception):
    """Base error carrying an exit code, stable machine code, and human hint."""

    exit_code: ExitCode = ExitCode.INTERNAL
    code: str = "internal"
    default_hint: str = "Consult documentation or re-run with --debug for details."

    def __init__(self, message: str, *, hint: str = "") -> None:
        """Attach a human hint alongside the exception message."""
        super().__init__(message)
        self.hint: Final[str] = hint or getattr(self, "default_hint", "")

    @property
    def message(self) -> str:
        """Human-readable primary message (``str(exc)``)."""
        return str(self)


class UsageError(VhecfsckError):
    """Bad flags, config, or caller misuse."""

    exit_code = ExitCode.USAGE
    code = "usage"
    default_hint = (
        "Check CLI usage and flags with --help, or consult the documentation."
    )


class TargetConnectionError(VhecfsckError):
    """Could not reach or open the audit target."""

    exit_code = ExitCode.USAGE
    code = "target_connection"
    default_hint = (
        "Verify target URI syntax, hostname reachability, service status, "
        "and credentials."
    )


class CapabilityError(VhecfsckError):
    """Target lacks a capability required for a metric or command."""

    exit_code = ExitCode.INCONCLUSIVE
    code = "capability"
    default_hint = (
        "Verify target engine version, required engine extras, and role privileges."
    )


class InconclusiveError(VhecfsckError):
    """Audit ran but a verdict could not be established."""

    exit_code = ExitCode.INCONCLUSIVE
    code = "inconclusive"
    default_hint = (
        "Verify audit config, increase sample size/queries, or adjust thresholds."
    )


class ResourceError(VhecfsckError):
    """Resource ceiling exceeded or minimum viable sample exceeds memory limit."""

    exit_code = ExitCode.USAGE
    code = "resource_limit"
    default_hint = (
        "Increase --max-memory-mb or --max-seconds, or audit a smaller subset."
    )


class InternalError(VhecfsckError):
    """Unexpected internal failure (maps to sysexits EX_SOFTWARE)."""

    exit_code = ExitCode.INTERNAL
    code = "internal"
    default_hint = (
        "Re-run with --debug for a traceback and report an issue at "
        "https://github.com/hbauzan/vhecfsck/issues"
    )


def abort(code: ExitCode) -> None:
    """Terminate the process with ``code`` (only SystemExit raise site in-package)."""
    raise SystemExit(int(code))


def handle_uncaught(exc: BaseException, *, debug: bool = False) -> ExitCode:
    """Map any uncaught exception to an exit code; write a short stderr report.

    Users never see a raw traceback by default. Pass ``debug=True`` (CLI
    ``--debug``) to include the traceback for agents and bug reports.
    """
    if isinstance(exc, VhecfsckError):
        _emit_vhecfsck_error(exc, debug=debug)
        return exc.exit_code

    sys.stderr.write(
        "vhecfsck: internal error — an unexpected failure occurred.\n"
        "Re-run with --debug for a traceback, then file a bug report.\n"
    )
    if debug:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    return ExitCode.INTERNAL


def _emit_vhecfsck_error(exc: VhecfsckError, *, debug: bool) -> None:
    sys.stderr.write(f"vhecfsck: {exc.code}: {exc}\n")
    if exc.hint:
        sys.stderr.write(f"hint: {exc.hint}\n")
    if debug:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
