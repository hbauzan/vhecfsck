#!/usr/bin/env python3
"""Checkout-scoped process cleaner for vhecfsck.

Terminates orphaned pytest, python, make, or uv test processes running against this checkout.
Uses stdlib only (`ps`, `os`, `signal`) for native execution on macOS and Linux.
Respects `SETUP_SH_IN_TEST=1` to remain safe during automated test suites.

The scan must never kill the process tree that launched it. A shell invoked as
``cd /path/to/checkout && make verify`` has both ``make `` and the checkout
path on its command line; excluding only ``self`` and ``getppid()`` leaves that
shell eligible (P9-13). The exclusion set is the full ancestor chain.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ProcessRow = tuple[int, int, str]


def _read_process_table() -> list[ProcessRow]:
    """Snapshot of ``pid, ppid, command`` from ``ps``. Empty on failure."""
    try:
        res = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        return []
    return _parse_process_table(res.stdout)


def _parse_process_table(ps_stdout: str) -> list[ProcessRow]:
    rows: list[ProcessRow] = []
    for line in ps_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        rows.append((pid, ppid, parts[2]))
    return rows


def ancestor_pids(
    start_pid: int,
    ppid_by_pid: Mapping[int, int] | None = None,
) -> set[int]:
    """Return ``start_pid`` and every parent up to pid 1, guarding cycles."""
    if ppid_by_pid is None:
        ppid_by_pid = {pid: ppid for pid, ppid, _cmd in _read_process_table()}
    seen: set[int] = set()
    pid = start_pid
    while pid > 1 and pid not in seen:
        seen.add(pid)
        parent = ppid_by_pid.get(pid)
        if parent is None or parent <= 1:
            if parent == 1:
                seen.add(1)
            break
        pid = parent
    return seen


def get_checkout_orphan_pids(root_dir: Path | None = None) -> list[int]:
    """Find PIDs of make/uv/python/pytest processes running within root_dir."""
    target_root = str((root_dir or ROOT).resolve())
    table = _read_process_table()
    ppid_by_pid = {pid: ppid for pid, ppid, _cmd in table}
    excluded = ancestor_pids(os.getpid(), ppid_by_pid)

    pids: list[int] = []
    for pid, _ppid, cmd in table:
        if pid in excluded:
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
