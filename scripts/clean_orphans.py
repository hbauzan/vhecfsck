#!/usr/bin/env python3
"""Checkout-scoped process cleaner for vhecfsck.

Terminates orphaned pytest, python, make, or uv test processes running against this checkout.
Uses stdlib only (`ps`, `os`, `signal`) for native execution on macOS and Linux.
Respects `SETUP_SH_IN_TEST=1` to remain safe during automated test suites.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_checkout_orphan_pids(root_dir: Path | None = None) -> list[int]:
    """Find PIDs of make/uv/python/pytest processes running within root_dir."""
    target_root = str((root_dir or ROOT).resolve())
    self_pid = os.getpid()
    parent_pid = os.getppid()

    try:
        res = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    pids: list[int] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue

        cmd = parts[1]
        if pid in (self_pid, parent_pid):
            continue

        # Match pytest, python, make, or uv process execution pointing to this checkout root
        is_relevant_cmd = any(
            token in cmd for token in ("pytest", "python", "make ", "make\t", "uv run")
        )
        if is_relevant_cmd and target_root in cmd:
            # Exclude this clean_orphans script itself
            if "clean_orphans.py" in cmd:
                continue
            pids.append(pid)

    return pids


def clean_checkout_orphans(root_dir: Path | None = None) -> int:
    """Terminate checkout-scoped orphan processes."""
    if (
        os.environ.get("SETUP_SH_IN_TEST") == "1"
        or os.environ.get("CLEAN_ORPHANS_IN_TEST") == "1"
    ):
        print("[clean-proc] Running inside test harness — skipping process cleanup.")
        return 0

    pids = get_checkout_orphan_pids(root_dir)
    if not pids:
        print("[clean-proc] No orphaned checkout processes found.")
        return 0

    print(f"[clean-proc] Terminating checkout-scoped processes (PIDs: {pids})...")

    # Send SIGTERM first
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as err:
            print(f"[clean-proc] Warning: permission denied killing PID {pid}: {err}")

    time.sleep(0.3)

    # Check if any remain and send SIGKILL
    remaining = [pid for pid in pids if _is_pid_running(pid)]
    if remaining:
        print(
            f"[clean-proc] Forcefully killing lingering processes (PIDs: {remaining})..."
        )
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as err:
                print(
                    f"[clean-proc] Warning: permission denied killing PID {pid}: {err}"
                )

    print("[clean-proc] Process cleanup finished successfully.")
    return 0


def _is_pid_running(pid: int) -> bool:
    """Check if a PID is still alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


if __name__ == "__main__":
    raise SystemExit(clean_checkout_orphans())
