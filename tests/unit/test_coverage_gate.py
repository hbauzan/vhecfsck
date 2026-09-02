"""TH-04: local .coverage cache; CI/merge always traces."""

from __future__ import annotations

from pathlib import Path

from scripts.coverage_gate import (
    META_NAME,
    cache_forced_off,
    cache_is_hit,
    core_report_argv,
    fingerprint,
    instrumented_pytest_argv,
    overall_report_argv,
    write_cache_meta,
)


def test_meta_filename_is_not_a_coverage_data_glob() -> None:
    """coverage.py treats ``.coverage.*`` as parallel data files."""
    assert not META_NAME.startswith(".coverage.")


def test_ci_and_opt_out_force_a_fresh_trace() -> None:
    assert cache_forced_off({"GITHUB_ACTIONS": "true"}) is True
    assert cache_forced_off({"CI": "true"}) is True
    assert cache_forced_off({"COVERAGE_CACHE": "0"}) is True
    assert cache_forced_off({"COVERAGE_CACHE": "false"}) is True
    assert cache_forced_off({}) is False


def test_fingerprint_ignores_ide_and_coverage_artifacts(tmp_path: Path) -> None:
    (tmp_path / "vhecfsck").mkdir()
    (tmp_path / "vhecfsck" / "mod.py").write_text("a = 1\n", encoding="utf-8")
    base = fingerprint(tmp_path)
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "x").write_text("nope\n", encoding="utf-8")
    (tmp_path / ".coverage").write_bytes(b"x")
    (tmp_path / ".coverage-cache.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "coverage.xml").write_text("<c/>\n", encoding="utf-8")
    assert fingerprint(tmp_path) == base


def test_fingerprint_changes_when_a_file_changes(tmp_path: Path) -> None:
    (tmp_path / "vhecfsck").mkdir()
    probe = tmp_path / "vhecfsck" / "mod.py"
    probe.write_text("a = 1\n", encoding="utf-8")
    first = fingerprint(tmp_path)
    probe.write_text("a = 2\n", encoding="utf-8")
    assert fingerprint(tmp_path) != first


def test_cache_hit_requires_coverage_data_and_matching_meta(tmp_path: Path) -> None:
    (tmp_path / "vhecfsck").mkdir()
    (tmp_path / "vhecfsck" / "mod.py").write_text("a = 1\n", encoding="utf-8")
    env: dict[str, str] = {}
    assert cache_is_hit(tmp_path, env=env, cov_all=80, cov_core=90) is False

    (tmp_path / ".coverage").write_bytes(b"not-a-real-db-but-present")
    assert cache_is_hit(tmp_path, env=env, cov_all=80, cov_core=90) is False

    write_cache_meta(tmp_path, fingerprint(tmp_path), cov_all=80, cov_core=90)
    assert cache_is_hit(tmp_path, env=env, cov_all=80, cov_core=90) is True
    assert cache_is_hit(tmp_path, env=env, cov_all=81, cov_core=90) is False
    assert (
        cache_is_hit(
            tmp_path,
            env={"GITHUB_ACTIONS": "true"},
            cov_all=80,
            cov_core=90,
        )
        is False
    )


def test_instrumented_miss_path_is_one_pytest_and_core_report() -> None:
    pytest_cmd = instrumented_pytest_argv(
        pkg="vhecfsck",
        cov_all=80,
        slow_marks="slow or integration or perf",
    )
    assert pytest_cmd.count("-m") >= 1
    assert pytest_cmd.count("pytest") == 1 or pytest_cmd[1] == "pytest"
    assert "--cov=vhecfsck" in pytest_cmd
    assert "--cov-fail-under=80" in pytest_cmd
    assert pytest_cmd.count("--cov-fail-under=80") == 1
    core = core_report_argv(core="vhecfsck/core", cov_core=90)
    assert "--fail-under=90" in core
    assert any(part.startswith("--include=") for part in core)
    overall = overall_report_argv(cov_all=80)
    assert "--fail-under=80" in overall
