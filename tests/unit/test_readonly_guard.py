"""P0-09: read-only AST guard."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_readonly.py"
ADAPTERS = ROOT / "vhecfsck" / "adapters"


def _run_guard() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_guard_passes_on_clean_tree() -> None:
    result = _run_guard()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "exemptions: none" in result.stdout


def test_client_delete_fails() -> None:
    probe = ADAPTERS / "_p0_09_delete_probe.py"
    probe.write_text(
        textwrap.dedent(
            """\
            class Client:
                def delete(self, x):
                    return x

            def bad(client: Client) -> None:
                client.delete(1)
            """
        ),
        encoding="utf-8",
    )
    try:
        result = _run_guard()
        assert result.returncode != 0
        assert "delete" in result.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_string_or_comment_does_not_fail() -> None:
    probe = ADAPTERS / "_p0_09_string_probe.py"
    probe.write_text(
        textwrap.dedent(
            '''\
            """Docs may mention delete without calling it."""

            HINT = "never call client.delete on production"
            # client.delete(1)
            '''
        ),
        encoding="utf-8",
    )
    try:
        result = _run_guard()
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        probe.unlink(missing_ok=True)


def test_aliased_write_fails() -> None:
    probe = ADAPTERS / "_p0_09_alias_probe.py"
    probe.write_text(
        textwrap.dedent(
            """\
            def bad(tbl) -> None:
                f = tbl.delete
                f()
            """
        ),
        encoding="utf-8",
    )
    try:
        result = _run_guard()
        assert result.returncode != 0
        assert "aliased" in result.stdout or "delete" in result.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_exemption_passes_and_appears_in_summary() -> None:
    probe = ADAPTERS / "_p0_09_exempt_probe.py"
    probe.write_text(
        textwrap.dedent(
            """\
            def documented(tbl) -> None:
                tbl.delete(1)  # readonly-ok: fixture-only probe for the guard itself
            """
        ),
        encoding="utf-8",
    )
    try:
        result = _run_guard()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "exempt" in result.stdout
        assert "fixture-only" in result.stdout
    finally:
        probe.unlink(missing_ok=True)


def test_guard_runs_under_two_seconds() -> None:
    started = time.perf_counter()
    result = _run_guard()
    elapsed = time.perf_counter() - started
    assert result.returncode == 0
    assert elapsed < 2.0, f"readonly guard took {elapsed:.2f}s"
