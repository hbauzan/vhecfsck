# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""P7-01: container harness contracts that do not need a live daemon."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.integration.containers import (
    PGVECTOR_IMAGE,
    QDRANT_IMAGE,
    docker_daemon_reachable,
    invocation_is_integration_dir,
    postgres_container_session,
    qdrant_container_session,
    require_docker,
    require_optional_import,
)
from tests.integration.seeding import SeedSpec, build_seed_plan
from vhecfsck.models import MetricSpace

ROOT = Path(__file__).resolve().parents[2]
CONTAINERS_SRC = ROOT / "tests" / "integration" / "containers.py"
SEEDING_SRC = ROOT / "tests" / "integration" / "seeding.py"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
ADR_0018 = ROOT / "roadmap" / "adr" / "0018-testcontainers-dev-dependency.md"


def _clear_ci_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_pinned_images_are_versioned_not_latest() -> None:
    assert QDRANT_IMAGE == "qdrant/qdrant:v1.19.0"
    assert PGVECTOR_IMAGE == "pgvector/pgvector:0.8.6-pg16"
    for image in (QDRANT_IMAGE, PGVECTOR_IMAGE):
        assert ":" in image
        _name, tag = image.rsplit(":", 1)
        assert _name
        assert tag
        assert tag != "latest"


def test_harness_uses_wait_strategies_not_sleep() -> None:
    source = CONTAINERS_SRC.read_text(encoding="utf-8")
    assert "time.sleep(" not in source
    assert "waiting_for(" in source
    assert "HttpWaitStrategy" in source
    assert "ExecWaitStrategy" in source
    assert "with_bind_ports" not in source
    assert "with_exposed_ports" in source


def test_seeding_module_lives_outside_the_package() -> None:
    rel = SEEDING_SRC.resolve().relative_to(ROOT)
    assert rel.parts[0] == "tests"
    assert "vhecfsck" not in rel.parts


def test_seed_plan_is_deterministic_under_fixed_seed() -> None:
    spec = SeedSpec(n=16, dim=4, seed=7, n_delete=3, n_update=1, name="det")
    a = build_seed_plan(spec)
    b = build_seed_plan(spec)
    assert a.corpus.vectors.shape == (16, 4)
    assert (a.corpus.vectors == b.corpus.vectors).all()
    assert (a.corpus.ids == b.corpus.ids).all()
    assert a.deleted_ids == b.deleted_ids == (13, 14, 15)
    assert a.updated_ids == b.updated_ids == (12,)
    assert (a.update_vectors == b.update_vectors).all()
    assert a.update_vectors.shape == (1, 4)


def test_seed_plan_changes_when_seed_changes() -> None:
    a = build_seed_plan(SeedSpec(n=16, dim=4, seed=1, name="a"))
    b = build_seed_plan(SeedSpec(n=16, dim=4, seed=2, name="b"))
    assert not (a.corpus.vectors == b.corpus.vectors).all()


def test_seed_plan_maps_metric_spaces() -> None:
    plan = build_seed_plan(SeedSpec(metric_space=MetricSpace.L2, n=8, n_delete=0))
    assert plan.spec.metric_space is MetricSpace.L2


def test_require_docker_skips_locally_when_daemon_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ci_env(monkeypatch)
    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: False
    )
    with pytest.raises(pytest.skip.Exception, match="Docker daemon"):
        require_docker()


def test_require_docker_fails_in_ci_when_daemon_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: False
    )
    with pytest.raises(pytest.fail.Exception, match="Docker daemon"):
        require_docker()


def test_require_docker_is_silent_when_daemon_is_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: True
    )
    require_docker()


def test_require_optional_import_skips_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ci_env(monkeypatch)
    with pytest.raises(pytest.skip.Exception, match="uv sync --group dev --extra"):
        require_optional_import("vhecfsck_no_such_engine_sdk", extra="qdrant")


def test_require_optional_import_fails_in_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception, match="uv sync --group dev --extra"):
        require_optional_import("vhecfsck_no_such_engine_sdk", extra="postgres")


def test_docker_daemon_reachable_returns_a_bool() -> None:
    assert docker_daemon_reachable() in {True, False}


def test_qdrant_context_stops_container_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[bool] = []

    class FakeContainer:
        def start(self) -> FakeContainer:
            return self

        def stop(self) -> None:
            stopped.append(True)

        def get_container_host_ip(self) -> str:
            return "127.0.0.1"

        def get_exposed_port(self, port: int) -> int:
            return 60000 + int(port)

    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: True
    )
    monkeypatch.setattr(
        "tests.integration.containers._make_qdrant_container", FakeContainer
    )
    with qdrant_container_session() as svc:
        assert svc.host == "127.0.0.1"
        assert svc.http_port == 66333
        assert svc.http_url == "http://127.0.0.1:66333"
    assert stopped == [True]


def test_qdrant_context_stops_container_when_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[bool] = []

    class FakeContainer:
        def start(self) -> FakeContainer:
            raise RuntimeError("boom")

        def stop(self) -> None:
            stopped.append(True)

    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: True
    )
    monkeypatch.setattr(
        "tests.integration.containers._make_qdrant_container", FakeContainer
    )
    with pytest.raises(RuntimeError, match="boom"), qdrant_container_session():
        raise AssertionError("must not yield")
    assert stopped == [True]


def test_postgres_context_stops_container_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[bool] = []

    class FakeContainer:
        def start(self) -> FakeContainer:
            return self

        def stop(self) -> None:
            stopped.append(True)

        def get_container_host_ip(self) -> str:
            return "127.0.0.1"

        def get_exposed_port(self, port: int) -> int:
            del port
            return 55432

    monkeypatch.setattr(
        "tests.integration.containers.docker_daemon_reachable", lambda: True
    )
    monkeypatch.setattr(
        "tests.integration.containers._make_postgres_container", FakeContainer
    )
    with postgres_container_session() as svc:
        assert svc.port == 55432
        assert "55432" in svc.dsn
        assert "postgresql://" in svc.dsn
    assert stopped == [True]


def test_invocation_is_integration_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    root = SimpleNamespace(rootpath=ROOT, args=["tests/integration"])
    assert invocation_is_integration_dir(root)
    assert invocation_is_integration_dir(
        SimpleNamespace(rootpath=ROOT, args=["tests/integration/test_harness.py"])
    )
    assert invocation_is_integration_dir(
        SimpleNamespace(
            rootpath=ROOT,
            args=["tests/integration/test_harness.py::test_qdrant_container_is_ready"],
        )
    )
    assert not invocation_is_integration_dir(SimpleNamespace(rootpath=ROOT, args=[]))
    assert not invocation_is_integration_dir(
        SimpleNamespace(rootpath=ROOT, args=["tests/unit"])
    )
    assert not invocation_is_integration_dir(
        SimpleNamespace(rootpath=ROOT, args=["tests/integration", "tests/unit"])
    )


def test_pytest_tests_integration_collects_marked_harness_tests() -> None:
    """Default addopts exclude ``integration``; the directory path re-enables them."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/test_harness.py",
            "--collect-only",
            "-q",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "test_qdrant_container_is_ready" in combined
    assert "test_postgres_container_accepts_tcp" in combined


def test_ci_recipe_documents_pinned_images() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert QDRANT_IMAGE in text
    assert PGVECTOR_IMAGE in text
    assert "--extra qdrant" in text
    assert "--extra postgres" in text


def test_adr_0018_exists() -> None:
    text = ADR_0018.read_text(encoding="utf-8")
    assert "testcontainers" in text.lower()
    assert "dependency-groups" in text or "dev" in text
    assert "Accepted" in text
