#!/usr/bin/env python3
"""Local .coverage cache for ``make coverage`` / ``make verify``.

Merge and CI always run one instrumented pytest and both floors (80 overall,
90 core/). Locally, an unchanged tree reuses ``.coverage`` and only reports.
``make test`` remains the uninstrumented inner loop. Force a trace with
``COVERAGE_CACHE=0``.

On Python 3.12+ the instrumented child uses ``COVERAGE_CORE=sysmon`` unless
that variable is already set (escape hatch: ``COVERAGE_CORE=ctrace``).
Python 3.11 keeps coverage.py's C tracer. Do not raise ``requires-python``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import coverage

ROOT = Path(__file__).resolve().parents[1]
META_NAME = ".coverage-cache.json"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "htmlcov",
        "site",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".import_linter_cache",
        ".tox",
        ".nox",
        ".hypothesis",
        ".cache",
        ".worktrees",
        "playwright-report",
        "test-results",
        ".cursor",
        ".agents",
        ".claude",
        ".idea",
        ".vscode",
        "scratch",
    }
)
_SKIP_NAMES = frozenset(
    {".coverage", "coverage.xml", ".DS_Store", ".coverage-cache.json"}
)
_SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".so"})


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in _TRUE


def cache_forced_off(env: Mapping[str, str]) -> bool:
    """CI/merge and explicit opt-out never reuse a cached trace."""
    if _truthy(env.get("GITHUB_ACTIONS", "")) or _truthy(env.get("CI", "")):
        return True
    return env.get("COVERAGE_CACHE", "").strip().lower() in _FALSE


def coverage_core_env(
    env: Mapping[str, str],
    *,
    version_info: tuple[int, ...] | None = None,
) -> dict[str, str]:
    """Copy ``env``; on 3.12+ set ``COVERAGE_CORE=sysmon`` unless already set."""
    out = dict(env)
    if out.get("COVERAGE_CORE", "").strip():
        return out
    info = sys.version_info if version_info is None else version_info
    if (int(info[0]), int(info[1])) >= (3, 12):
        out["COVERAGE_CORE"] = "sysmon"
    return out


def _skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in _SKIP_DIRS for part in rel_parts):
        return True
    name = path.name
    if name in _SKIP_NAMES or name.startswith(".coverage."):
        return True
    return path.suffix in _SKIP_SUFFIXES


def fingerprint(root: Path) -> str:
    """Stable hash of the tree that can change tests or coverage."""
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file() and not _skip(p, root))
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_cache_meta(
    root: Path,
    tree_fingerprint: str,
    *,
    cov_all: int,
    cov_core: int,
) -> None:
    payload = {
        "coverage_version": coverage.__version__,
        "cov_all": int(cov_all),
        "cov_core": int(cov_core),
        "fingerprint": tree_fingerprint,
        "python": sys.version,
    }
    (root / META_NAME).write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def cache_is_hit(
    root: Path,
    *,
    env: Mapping[str, str],
    cov_all: int,
    cov_core: int,
) -> bool:
    if cache_forced_off(env):
        return False
    if not (root / ".coverage").is_file() or not (root / META_NAME).is_file():
        return False
    try:
        meta = json.loads((root / META_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    try:
        meta_all = int(meta["cov_all"])
        meta_core = int(meta["cov_core"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        meta.get("fingerprint") == fingerprint(root)
        and meta_all == int(cov_all)
        and meta_core == int(cov_core)
        and meta.get("python") == sys.version
        and meta.get("coverage_version") == coverage.__version__
    )


def instrumented_pytest_argv(
    *,
    pkg: str,
    cov_all: int,
    slow_marks: str,
) -> list[str]:
    """One instrumented default-suite pytest; overall floor is ``--cov-fail-under``."""
    return [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        f"not ({slow_marks})",
        f"--cov={pkg}",
        "--cov-report=term-missing",
        "--cov-report=xml",
        f"--cov-fail-under={cov_all}",
        "-q",
    ]


def overall_report_argv(*, cov_all: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--fail-under={cov_all}",
    ]


def core_report_argv(*, core: str, cov_core: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--include={core}/*",
        f"--fail-under={cov_core}",
    ]


def main() -> int:
    env = os.environ
    cov_all = int(env.get("COV_ALL", "80"))
    cov_core = int(env.get("COV_CORE", "90"))
    pkg = env.get("PKG", "vhecfsck")
    core = env.get("CORE", f"{pkg}/core")
    slow_marks = env.get("SLOW_MARKS", "slow or integration or perf")

    if cache_is_hit(env=env, root=ROOT, cov_all=cov_all, cov_core=cov_core):
        print(
            "coverage-gate: cache hit — reused .coverage "
            "(COVERAGE_CACHE=0 forces a trace)",
            file=sys.stderr,
        )
        overall = subprocess.run(overall_report_argv(cov_all=cov_all), cwd=ROOT)
        if overall.returncode != 0:
            return int(overall.returncode)
        core_run = subprocess.run(
            core_report_argv(core=core, cov_core=cov_core),
            cwd=ROOT,
        )
        return int(core_run.returncode)

    reason = "CI" if cache_forced_off(env) else "miss"
    pytest_env = coverage_core_env(env)
    # `core` is the package path for the 90% floor; do not reuse it for the tracer name.
    tracer = pytest_env.get("COVERAGE_CORE", "").strip() or "ctrace"
    print(
        f"coverage-gate: {reason} — instrumented pytest (COVERAGE_CORE={tracer})",
        file=sys.stderr,
    )
    traced = subprocess.run(
        instrumented_pytest_argv(pkg=pkg, cov_all=cov_all, slow_marks=slow_marks),
        cwd=ROOT,
        env=pytest_env,
    )
    if traced.returncode != 0:
        return int(traced.returncode)
    core_run = subprocess.run(
        core_report_argv(core=core, cov_core=cov_core),
        cwd=ROOT,
    )
    if core_run.returncode != 0:
        return int(core_run.returncode)
    write_cache_meta(
        ROOT,
        fingerprint(ROOT),
        cov_all=cov_all,
        cov_core=cov_core,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
