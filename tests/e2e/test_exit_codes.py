"""Exit-code contract test suite exercising real CLI subprocesses (P3-08)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXIT_CODE_CASES = [
    (
        0,
        [sys.executable, "-m", "vhecfsck", "demo", "--scenario", "healthy"],
        {},
    ),
    (
        2,
        [sys.executable, "-m", "vhecfsck", "demo", "--scenario", "tombstoned"],
        {},
    ),
    (
        3,
        [sys.executable, "-m", "vhecfsck", "demo", "--scenario", "tiny"],
        {},
    ),
    (
        4,
        [sys.executable, "-m", "vhecfsck", "audit", "--nonexistent-flag"],
        {},
    ),
    (
        70,
        [sys.executable, "-m", "vhecfsck", "demo"],
        {"_VHECFSCK_FAULT_INJECT": "1"},
    ),
]


@pytest.mark.parametrize("expected_code, cmd, extra_env", EXIT_CODE_CASES)
def test_cli_exit_code_contract_subprocesses(
    expected_code: int, cmd: list[str], extra_env: dict[str, str]
) -> None:
    env = dict(os.environ)
    env.update(extra_env)

    proc = subprocess.run(
        cmd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == expected_code, (
        f"Cmd {cmd} returned {proc.returncode}, expected {expected_code}.\n"
        f"Stdout: {proc.stdout}\nStderr: {proc.stderr}"
    )


def test_cli_exit_code_warn(tmp_path: Path) -> None:
    cfg_file = tmp_path / "warn_config.toml"
    cfg_file.write_text(
        "[thresholds.canary_recall]\nwarn = 0.99\nfail = 0.50\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "vhecfsck",
        "audit",
        "--target",
        "synthetic://healthy",
        "--config",
        str(cfg_file),
    ]
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, (
        f"Cmd {cmd} returned {proc.returncode}, expected 1.\n"
        f"Stdout: {proc.stdout}\nStderr: {proc.stderr}"
    )


def test_cli_quiet_mode_empty_stdout_stderr() -> None:
    cmd = [sys.executable, "-m", "vhecfsck", "--quiet", "demo", "--scenario", "healthy"]
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""
