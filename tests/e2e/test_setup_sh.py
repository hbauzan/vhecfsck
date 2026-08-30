"""Contributor console (`setup.sh`).

Public surface: `./setup.sh help|sync|verify|demo|serve|clean` and the
interactive menu. Exit codes follow the skill taxonomy (0 / 2 / 3 / 4). The
console is a contributor tool, not a daemon supervisor and not a product surface.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

_ANSI = re.compile(r"\033\[[0-9;]*m")

ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "setup.sh"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_INCONCLUSIVE = 3
EXIT_USAGE = 4

BANNER = "DON'T PANIC — Vector Index"
EXIT_LINE = "So long, and thanks for all the fish"
INVALID_LINE = "I think you ought to know I'm feeling very depressed."

REQUIRED_LABELS = (
    "Infinite Improbability Drive",
    "The mice would like a word",
    "Forty-two",
    "Heart of Gold",
    "Point-of-View Gun",
    EXIT_LINE,
)

FORBIDDEN_PRODUCT_COPY = (
    "Hugging Face",
    "huggingface",
    "Spaces",
    "Vite",
    ":5173",
    "Vogon constructor fleet",
    "The Guide has this to say",
)


def run_setup(
    *args: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.setdefault("SETUP_SH_UNAME", "Darwin")
    merged.setdefault("SETUP_SH_IN_TEST", "1")
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SETUP), *args],
        cwd=cwd or ROOT,
        env=merged,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def test_setup_sh_exists_and_is_executable() -> None:
    assert SETUP.is_file(), "setup.sh must live at the repository root"
    mode = SETUP.stat().st_mode
    assert mode & stat.S_IXUSR, "setup.sh must be executable"


def test_help_prints_banner_and_hitchhiker_labels() -> None:
    result = run_setup("help")
    assert result.returncode == EXIT_OK, result.stderr
    out = result.stdout
    assert BANNER in out
    for label in REQUIRED_LABELS:
        assert label in out, label


def test_help_puts_actions_before_hitchhiker_quotes() -> None:
    """Technical action is the primary text; Guide quotes are secondary."""
    result = run_setup("help")
    assert result.returncode == EXIT_OK, result.stderr
    plain = _ANSI.sub("", result.stdout)
    pairs = (
        ("detect uv, then uv sync", "Infinite Improbability Drive"),
        ("make verify", "The mice would like a word"),
        ("uv run vhecfsck demo", "Forty-two"),
        ("uv run vhecfsck serve", "Heart of Gold"),
        ("kill orphaned pytest processes for this checkout", "Point-of-View Gun"),
        ("Exit the panel", EXIT_LINE),
    )
    for action, quote in pairs:
        action_at = plain.index(action)
        quote_at = plain.index(quote)
        assert action_at < quote_at, (action, quote)


def test_clean_verb_exits_ok() -> None:
    result = run_setup("clean")
    assert result.returncode == EXIT_OK, result.stderr + result.stdout
    assert "Point-of-View Gun" in result.stdout
    assert "skipping process cleanup" in result.stdout


def test_clean_scopes_kill_to_this_checkout() -> None:
    source = SETUP.read_text(encoding="utf-8")
    assert "pkill" not in source
    assert "pgrep -f pytest" not in source
    assert "index($0, root)" in source
    assert 'index($0, "pytest")' in source


def test_help_does_not_advertise_saas_daemon_or_vite() -> None:
    result = run_setup("help")
    assert result.returncode == EXIT_OK, result.stderr
    blob = result.stdout + result.stderr
    for forbidden in FORBIDDEN_PRODUCT_COPY:
        assert forbidden not in blob, forbidden


def test_help_does_not_create_pid_or_log_directories() -> None:
    result = run_setup("help")
    assert result.returncode == EXIT_OK, result.stderr
    assert not (ROOT / ".pids").exists()
    assert not (ROOT / "logs").exists()


def test_unknown_verb_is_usage_error() -> None:
    result = run_setup("teleport")
    assert result.returncode == EXIT_USAGE
    assert INVALID_LINE in result.stderr or INVALID_LINE in result.stdout


def test_linux_is_inconclusive_until_publish_port() -> None:
    result = run_setup("help", env={"SETUP_SH_UNAME": "Linux"})
    assert result.returncode == EXIT_INCONCLUSIVE
    blob = result.stdout + result.stderr
    assert "macOS" in blob


def test_menu_exit_prints_fish_line() -> None:
    result = run_setup(input_text="0\n")
    assert result.returncode == EXIT_OK, result.stderr
    assert EXIT_LINE in result.stdout


def test_menu_invalid_option_stays_in_panel() -> None:
    result = run_setup(input_text="xyz\n0\n")
    assert result.returncode == EXIT_OK, result.stderr
    assert INVALID_LINE in result.stdout
    assert EXIT_LINE in result.stdout


def test_sync_invokes_uv_sync_without_all_extras(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv-args.txt"
    uv = bin_dir / "uv"
    uv.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\nexit 0\n',
        encoding="utf-8",
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)

    result = run_setup(
        "sync",
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "SETUP_SH_SKIP_PREREQ_PROMPT": "1",
        },
    )
    assert result.returncode == EXIT_OK, result.stderr + result.stdout
    recorded = log.read_text(encoding="utf-8")
    assert "sync" in recorded.split()
    assert "--all-extras" not in recorded


def test_verify_without_makefile_is_inconclusive(tmp_path: Path) -> None:
    result = run_setup("verify", cwd=tmp_path)
    assert result.returncode == EXIT_INCONCLUSIVE
    blob = result.stdout + result.stderr
    assert "This must be Thursday" in blob or "make verify" in blob


def test_verify_runs_make_verify_when_makefile_exists(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "verify:\n\t@echo mice-ok\n",
        encoding="utf-8",
    )
    result = run_setup("verify", cwd=tmp_path)
    assert result.returncode == EXIT_OK, result.stderr + result.stdout
    assert "mice-ok" in result.stdout


def test_verify_propagates_gate_failure(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "verify:\n\t@exit 2\n",
        encoding="utf-8",
    )
    result = run_setup("verify", cwd=tmp_path)
    assert result.returncode == EXIT_FAIL


def test_demo_runs_demo_command_when_it_exists() -> None:
    result = run_setup("demo")
    assert result.returncode == EXIT_FAIL
    blob = result.stdout + result.stderr
    assert "Forty-two" in blob
    assert "pgvector#244" in blob


def test_serve_is_inconclusive_until_the_command_exists() -> None:
    result = run_setup("serve")
    assert result.returncode == EXIT_INCONCLUSIVE
    blob = result.stdout + result.stderr
    assert "Heart of Gold" in blob or "serve" in blob


def test_script_source_forbids_daemon_and_saas_mechanics() -> None:
    source = SETUP.read_text(encoding="utf-8")
    assert "nohup" not in source
    assert ".pids" not in source
    assert "--all-extras" not in source
    assert "huggingface" not in source.lower()
    assert "uvicorn" not in source
    assert "pkill" not in source
