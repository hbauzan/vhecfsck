"""FastAPI application factory and server lifecycle for vhecfsck serve."""

from __future__ import annotations

import importlib
from typing import Any

from vhecfsck.errors import UsageError


def check_server_dependencies() -> None:
    """Verify that optional server dependencies (fastapi, uvicorn) are installed."""
    try:
        importlib.import_module("fastapi")
        importlib.import_module("uvicorn")
    except ImportError as exc:
        raise UsageError(
            "Server support is not installed",
            hint='pip install "vhecfsck[server]"',
        ) from exc


def create_app(
    target_uri: str | None = None,
    report_path: str | None = None,
) -> Any:
    """Create and configure the FastAPI server application.

    Args:
        target_uri: Optional target vector index URI.
        report_path: Optional path to pre-computed JSON report file.

    Returns:
        Configured FastAPI application instance.
    """
    check_server_dependencies()
    from fastapi import FastAPI

    from vhecfsck.server.routes import router

    app = FastAPI(
        title="vhecfsck 3D Visualizer",
        description="Topological Audit and 3D Visualizer Server",
        version="0.1.0",
    )
    app.state.target_uri = target_uri
    app.state.report_path = report_path
    app.state.audit_running = False
    app.include_router(router)

    return app
