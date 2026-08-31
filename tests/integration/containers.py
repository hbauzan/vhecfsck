# Copyright 2026 hbauzan
# SPDX-License-Identifier: Apache-2.0
"""Session-scoped testcontainers fixtures for Qdrant and PostgreSQL+pgvector.

Write-side helpers stay in ``tests/`` (ADR-0001). Image tags are pinned; startup
is wait-strategy gated (HTTP ``/readyz`` / ``pg_isready``), never a sleep call.
Host ports are ephemeral (``with_exposed_ports``) so collisions are Docker's
problem, not a hardcoded bind.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

QDRANT_IMAGE = "qdrant/qdrant:v1.19.0"
PGVECTOR_IMAGE = "pgvector/pgvector:0.8.6-pg16"
QDRANT_HTTP_PORT = 6333
QDRANT_GRPC_PORT = 6334
POSTGRES_PORT = 5432
STARTUP_TIMEOUT_S = 120
POSTGRES_USER = "test"
POSTGRES_PASSWORD = "test"
POSTGRES_DB = "test"


@dataclass(frozen=True)
class QdrantService:
    """Reachable Qdrant HTTP/gRPC endpoints from a session-scoped container."""

    host: str
    http_port: int
    grpc_port: int

    @property
    def http_url(self) -> str:
        """Base URL for REST, including the mapped host port."""
        return f"http://{self.host}:{self.http_port}"


@dataclass(frozen=True)
class PostgresService:
    """Reachable PostgreSQL+pgvector endpoint from a session-scoped container."""

    host: str
    port: int
    user: str
    password: str
    dbname: str

    @property
    def dsn(self) -> str:
        """libpq DSN for the throwaway test role (not a production secret)."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.dbname}"
        )


def running_in_ci() -> bool:
    """GitHub Actions sets ``CI`` and ``GITHUB_ACTIONS``; both count."""
    for key in ("CI", "GITHUB_ACTIONS"):
        raw = os.environ.get(key, "").strip().lower()
        if raw in {"1", "true", "yes"}:
            return True
    return False


def docker_daemon_reachable() -> bool:
    """Return True when the local Docker engine answers ping."""
    try:
        import docker
    except ImportError:
        return False
    try:
        client = docker.from_env()
    except Exception:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def require_docker() -> None:
    """Skip locally with an actionable message; fail the suite in CI."""
    if docker_daemon_reachable():
        return
    message = (
        "Docker daemon is not reachable. Container integration tests need a "
        "running engine (Docker Desktop on macOS, or "
        "`sudo systemctl start docker` on Linux). Then re-run: "
        "uv run pytest tests/integration -q --no-cov"
    )
    if running_in_ci():
        pytest.fail(message + " CI must not skip this suite.")
    pytest.skip(message)


def require_optional_import(module: str, *, extra: str) -> None:
    """Skip (local) or fail (CI) when an engine extra is missing."""
    try:
        __import__(module)
    except ImportError:
        message = (
            f"{module} is not installed. For container integration tests run "
            f"`uv sync --group dev --extra {extra}` "
            "(never `uv sync --all-extras`)."
        )
        if running_in_ci():
            pytest.fail(message)
        pytest.skip(message)


def invocation_is_integration_dir(config: pytest.Config) -> bool:
    """True when every pytest arg is under ``tests/integration``.

    Default addopts exclude the ``integration`` marker. Contributors run
    ``uv run pytest tests/integration`` and expect those tests to execute, so
    collection strips the marker for that invocation only.
    """
    root = Path(str(config.rootpath)).resolve()
    integration = root / "tests" / "integration"
    raw_args = list(getattr(config, "args", []) or [])
    if not raw_args:
        return False
    resolved: list[Path] = []
    cwd = Path.cwd()
    for arg in raw_args:
        file_part = str(arg).split("::", 1)[0]
        path = Path(file_part)
        path = path.resolve() if path.is_absolute() else (cwd / path).resolve()
        resolved.append(path)
    for path in resolved:
        try:
            path.relative_to(integration)
        except ValueError:
            if path != integration:
                return False
    return True


def _make_qdrant_container() -> object:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import HttpWaitStrategy

    return (
        DockerContainer(QDRANT_IMAGE)
        .with_exposed_ports(QDRANT_HTTP_PORT, QDRANT_GRPC_PORT)
        .waiting_for(
            HttpWaitStrategy(QDRANT_HTTP_PORT, "/readyz")
            .for_status_code(200)
            .with_startup_timeout(STARTUP_TIMEOUT_S)
        )
    )


def _make_postgres_container() -> object:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import ExecWaitStrategy

    return (
        DockerContainer(PGVECTOR_IMAGE)
        .with_env("POSTGRES_USER", POSTGRES_USER)
        .with_env("POSTGRES_PASSWORD", POSTGRES_PASSWORD)
        .with_env("POSTGRES_DB", POSTGRES_DB)
        .with_exposed_ports(POSTGRES_PORT)
        .waiting_for(
            ExecWaitStrategy(
                ["pg_isready", "-U", POSTGRES_USER, "-d", POSTGRES_DB]
            ).with_startup_timeout(STARTUP_TIMEOUT_S)
        )
    )


@contextmanager
def qdrant_container_session() -> Iterator[QdrantService]:
    """Start one Qdrant container; stop/remove it on exit."""
    require_docker()
    container = _make_qdrant_container()
    try:
        container.start()
        yield QdrantService(
            host=container.get_container_host_ip(),
            http_port=int(container.get_exposed_port(QDRANT_HTTP_PORT)),
            grpc_port=int(container.get_exposed_port(QDRANT_GRPC_PORT)),
        )
    finally:
        container.stop()


@contextmanager
def postgres_container_session() -> Iterator[PostgresService]:
    """Start one PostgreSQL+pgvector container; stop/remove it on exit."""
    require_docker()
    container = _make_postgres_container()
    try:
        container.start()
        yield PostgresService(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(POSTGRES_PORT)),
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB,
        )
    finally:
        container.stop()
