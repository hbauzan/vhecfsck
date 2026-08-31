"""P0-03: pytest harness and coverage gate contracts.

Encodes markers, addopts, coverage floors, directory skeleton, and
conftest determinism fixtures so a future edit cannot silently drop them.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"

REQUIRED_MARKERS = {
    "slow",
    "integration",
    "perf",
    "requires_docker",
    "requires_lancedb",
    "requires_qdrant",
    "requires_postgres",
}

REQUIRED_TEST_DIRS = (
    "unit",
    "property",
    "oracle",
    "contract",
    "integration",
    "e2e",
    "perf",
    "fixtures",
)

# Coverage subprocesses must not re-enter this module (nested pytest + cov).
_COVERAGE_TARGETS = (
    "tests/unit/test_package.py",
    "tests/unit/test_cli_stub.py",
    "tests/unit/test_errors.py",
    "tests/unit/test_config.py",
    "tests/unit/test_logging_redaction.py",
    "tests/unit/test_models.py",
    "tests/unit/test_metric_models.py",
    "tests/unit/test_scene_model.py",
    "tests/unit/test_scene_codec.py",
    "tests/unit/test_adapter_protocol.py",
    "tests/unit/test_generator.py",
    "tests/unit/test_pathologies.py",
    "tests/unit/test_synthetic_adapter.py",
    "tests/unit/test_registry.py",
    "tests/contract/test_adapter_contract.py",
    "tests/unit/test_scenarios.py",
    "tests/oracle/test_ground_truth.py",
    "tests/oracle/test_canary.py",
    "tests/oracle/test_hubness.py",
    "tests/property/test_hubness_props.py",
    "tests/unit/test_fragmentation.py",
    "tests/unit/test_partitions.py",
    "tests/unit/test_verdict.py",
    "tests/unit/test_pipeline.py",
    "tests/unit/test_canary_groups.py",
    "tests/unit/test_sampling.py",
    "tests/unit/test_projection.py",
    "tests/unit/test_lod.py",
    "tests/unit/test_lod_chunking.py",
    "tests/unit/test_probe.py",
    "tests/unit/test_scene_views.py",
    "tests/unit/test_tombstones.py",
    "tests/unit/test_camera.py",
    "tests/unit/test_scene_service.py",
    "tests/unit/test_probe_service.py",
    "tests/unit/test_demo_capture.py",
    "tests/unit/test_qdrant_adapter.py",
    "tests/unit/test_postgres_adapter.py",
    "tests/property/test_canary_props.py",
    "tests/property/test_partitions_props.py",
    "tests/property/test_projection_props.py",
    "tests/property/test_determinism.py",
    "tests/property/test_fuzz.py",
    "tests/e2e/test_cli_audit.py",
    "tests/e2e/test_cli_demo.py",
    "tests/e2e/test_prometheus.py",
    "tests/e2e/test_cli_export.py",
    "tests/e2e/test_exit_codes.py",
    "tests/e2e/test_cli_serve.py",
    "tests/unit/test_build_hook.py",
)

# Nightly core-floor subprocess (P0-04 / lesson 35). Keep in sync with
# ``test_core_coverage_gate_passes``.
_CORE_COVERAGE_TARGETS = (
    "tests/oracle/test_ground_truth.py",
    "tests/oracle/test_canary.py",
    "tests/oracle/test_hubness.py",
    "tests/property/test_hubness_props.py",
    "tests/property/test_canary_props.py",
    "tests/property/test_partitions_props.py",
    "tests/property/test_projection_props.py",
    "tests/property/test_fuzz.py",
    "tests/unit/test_fragmentation.py",
    "tests/unit/test_partitions.py",
    "tests/unit/test_verdict.py",
    "tests/unit/test_pipeline.py",
    "tests/unit/test_canary_groups.py",
    "tests/unit/test_sampling.py",
    "tests/unit/test_projection.py",
    "tests/unit/test_lod.py",
    "tests/unit/test_lod_chunking.py",
    "tests/unit/test_probe.py",
    "tests/unit/test_scene_views.py",
    "tests/unit/test_tombstones.py",
    "tests/unit/test_camera.py",
    "tests/unit/test_scene_service.py",
    "tests/unit/test_probe_service.py",
    "tests/unit/test_demo_capture.py",
    "tests/unit/test_qdrant_adapter.py",
    "tests/unit/test_postgres_adapter.py",
)

_COVERAGE_SCAN_SKIP = frozenset(
    {
        "tests/unit/test_harness_config.py",
    }
)
_COVERAGE_SCAN_SKIP_DIRS = frozenset({"e2e", "perf", "fixtures", "integration"})
_CORE_IMPORT_RE = re.compile(r"^(?:from|import)\s+vhecfsck\.core\b", re.MULTILINE)


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def _pytest_addopts() -> list[str]:
    raw = _load_pyproject()["tool"]["pytest"]["ini_options"].get("addopts", [])
    if isinstance(raw, str):
        return raw.split()
    return list(raw)


def test_pytest_addopts_enables_strict_markers_config_and_ra() -> None:
    addopts = _pytest_addopts()
    joined = " ".join(addopts)
    assert "--strict-markers" in addopts or "--strict-markers" in joined
    assert "--strict-config" in addopts or "--strict-config" in joined
    assert "-ra" in addopts or "-ra" in joined


def test_default_run_excludes_slow_integration_and_perf() -> None:
    joined = " ".join(_pytest_addopts())
    assert "-m" in joined or any(part.startswith("-m") for part in _pytest_addopts())
    assert "not slow" in joined
    assert "not integration" in joined
    assert "not perf" in joined


def test_registered_markers_include_required_set() -> None:
    markers = _load_pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    names: set[str] = set()
    for entry in markers:
        name = entry.split(":", 1)[0].strip()
        names.add(name)
    missing = REQUIRED_MARKERS - names
    assert not missing, f"pytest markers missing: {sorted(missing)}"


def test_coverage_fail_under_overall_is_80() -> None:
    report = _load_pyproject()["tool"]["coverage"]["report"]
    assert report.get("fail_under") == 80


def test_pytest_cov_is_a_dev_dependency() -> None:
    dev = _load_pyproject()["dependency-groups"]["dev"]
    assert any(dep.startswith("pytest-cov") for dep in dev)


def test_engine_extras_declare_sdks() -> None:
    extras = _load_pyproject()["project"]["optional-dependencies"]
    qdrant = extras["qdrant"]
    postgres = extras["postgres"]
    assert any("qdrant-client" in dep for dep in qdrant)
    assert any("psycopg" in dep for dep in postgres)
    assert any("pgvector" in dep for dep in postgres)


def test_testcontainers_is_dev_not_product_extra() -> None:
    data = _load_pyproject()
    dev = data["dependency-groups"]["dev"]
    assert any(dep.startswith("testcontainers") for dep in dev)
    extras = data["project"]["optional-dependencies"]
    for name, deps in extras.items():
        assert all("testcontainers" not in dep for dep in deps), name


def test_test_directory_skeleton_exists() -> None:
    tests_root = ROOT / "tests"
    missing = [name for name in REQUIRED_TEST_DIRS if not (tests_root / name).is_dir()]
    assert not missing, f"missing test dirs: {missing}"


def test_conftest_provides_rng_and_deterministic_env(rng, deterministic_env) -> None:
    del deterministic_env  # autouse; fixture must be resolvable by name
    sample_a = rng.integers(0, 1_000_000, size=4)
    sample_b = rng.integers(0, 1_000_000, size=4)
    assert sample_a.shape == (4,)
    assert (sample_a != sample_b).any()
    assert os.environ.get("PYTHONHASHSEED") == "0"
    assert os.environ.get("OMP_NUM_THREADS") == "1"


def test_rng_is_seeded_reproducibly(rng) -> None:
    # Fresh generator with the same seed must match the fixture's first draw.
    import numpy as np

    expected = np.random.default_rng(0).integers(0, 1_000_000, size=8)
    got = rng.integers(0, 1_000_000, size=8)
    assert (got == expected).all()


def test_slow_marker_is_registered_and_selectable() -> None:
    """``slow`` is a registered marker; suite may collect zero or more slow tests."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            "slow",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    # pytest exits 5 when the selection is empty; 0 when at least one matches.
    assert result.returncode in {0, 5}, combined
    assert "unknown marker" not in combined.lower()


def test_unregistered_marker_fails_collection(tmp_path: Path) -> None:
    probe = tmp_path / "test_bad_marker_probe.py"
    probe.write_text(
        textwrap.dedent(
            """\
            import pytest

            @pytest.mark.not_a_registered_marker
            def test_probe():
                assert True
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--strict-markers",
            "--strict-config",
            "--rootdir",
            str(ROOT),
            "-c",
            str(PYPROJECT),
            "--override-ini=addopts=",
            "--collect-only",
            "-q",
            str(probe),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined
    assert "not_a_registered_marker" in combined


def test_coverage_targets_include_core_importing_modules() -> None:
    """Fast contract: nightly lists stay complete when core/ grows (lesson 35)."""
    missing_overall: list[str] = []
    missing_core: list[str] = []
    tests_root = ROOT / "tests"
    for path in sorted(tests_root.rglob("test_*.py")):
        rel = str(path.relative_to(ROOT))
        if rel in _COVERAGE_SCAN_SKIP:
            continue
        if path.parent.name in _COVERAGE_SCAN_SKIP_DIRS:
            continue
        text = path.read_text(encoding="utf-8")
        if _CORE_IMPORT_RE.search(text) is None:
            continue
        if rel not in _COVERAGE_TARGETS:
            missing_overall.append(rel)
        if rel not in _CORE_COVERAGE_TARGETS:
            missing_core.append(rel)
    assert not missing_overall, f"add to _COVERAGE_TARGETS: {missing_overall}"
    assert not missing_core, f"add to _CORE_COVERAGE_TARGETS: {missing_core}"


@pytest.mark.slow
def test_overall_coverage_gate_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not slow and not integration and not perf",
            "--cov=vhecfsck",
            "--cov-fail-under=80",
            "--override-ini=addopts=",
            "-q",
            *_COVERAGE_TARGETS,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined


@pytest.mark.slow
def test_core_coverage_gate_passes() -> None:
    """Separate core/-scoped invocation at fail_under=90 (contract / P0-04)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=vhecfsck.core",
            "--cov-fail-under=90",
            "--override-ini=addopts=",
            "-q",
            *_CORE_COVERAGE_TARGETS,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined


def test_nested_coverage_gate_tests_are_marked_slow() -> None:
    """Nested pytest-cov must not run inside the default gate (hangs the host)."""
    overall_marks = {mark.name for mark in test_overall_coverage_gate_passes.pytestmark}
    core_marks = {mark.name for mark in test_core_coverage_gate_passes.pytestmark}
    assert "slow" in overall_marks
    assert "slow" in core_marks


def _extract_module_markers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    markers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    values = (
                        node.value.elts
                        if isinstance(node.value, ast.List)
                        else [node.value]
                    )
                    for val in values:
                        if (
                            isinstance(val, ast.Attribute)
                            and isinstance(val.value, ast.Attribute)
                            and val.value.attr == "mark"
                        ):
                            markers.add(val.attr)
                        elif (
                            isinstance(val, ast.Call)
                            and isinstance(val.func, ast.Attribute)
                            and isinstance(val.func.value, ast.Attribute)
                            and val.func.value.attr == "mark"
                        ):
                            markers.add(val.func.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                d_val = decorator.func if isinstance(decorator, ast.Call) else decorator
                if (
                    isinstance(d_val, ast.Attribute)
                    and isinstance(d_val.value, ast.Attribute)
                    and d_val.value.attr == "mark"
                ):
                    markers.add(d_val.attr)
    return markers


def test_integration_qdrant_postgres_tests_have_integration_marker() -> None:
    """Non-docker integration tests declaring qdrant/postgres must have mark."""
    integration_dir = ROOT / "tests" / "integration"
    unmarked_files: list[str] = []
    for path in sorted(integration_dir.glob("test_*.py")):
        markers = _extract_module_markers(path)
        requires_qdrant_or_pg = (
            "requires_qdrant" in markers or "requires_postgres" in markers
        )
        if (
            requires_qdrant_or_pg
            and "requires_docker" not in markers
            and "integration" not in markers
        ):
            unmarked_files.append(path.name)
    assert not unmarked_files, (
        f"Integration test files missing 'integration' mark: {unmarked_files}"
    )
