"""API route definitions for vhecfsck embedded web visualizer server (P4-05)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request, Response

from vhecfsck.adapters.registry import open_target
from vhecfsck.config import load_config
from vhecfsck.core.lod import decimate
from vhecfsck.core.projection import project_to_3d
from vhecfsck.models.report import report_to_dict
from vhecfsck.models.scene import LodMetadata, PointClass, ScenePayload
from vhecfsck.pipeline import run_audit
from vhecfsck.report.prometheus import render_prometheus
from vhecfsck.report.scene_codec import encode_scene_binary

router = APIRouter()


@router.get("/api/health")
def get_health(request: Request) -> dict[str, str]:
    """Liveness probe endpoint."""
    target = getattr(request.app.state, "target_uri", None) or ""
    return {"status": "ok", "target": target}


@router.get("/api/report")
def get_report(request: Request) -> dict[str, Any]:
    """Return JSON audit report data."""
    report_path = getattr(request.app.state, "report_path", None)
    target_uri = getattr(request.app.state, "target_uri", None)

    if report_path and Path(report_path).exists():
        text = Path(report_path).read_text(encoding="utf-8")
        return json.loads(text)  # type: ignore[no-any-return]

    if target_uri:
        adapter = open_target(target_uri)
        try:
            config = load_config()
            report = run_audit(adapter, config)
            return report_to_dict(report)
        finally:
            if hasattr(adapter, "close"):
                adapter.close()

    raise HTTPException(status_code=404, detail="No report or target URI configured")


@router.get("/api/scene")
def get_scene(
    request: Request,
    budget: int = Query(200000, ge=10, le=1000000),
) -> Response:
    """Return binary octet-stream 3D scene payload."""
    target_uri = getattr(request.app.state, "target_uri", None)
    if not target_uri:
        empty_scene = ScenePayload(
            positions=np.empty((0, 3), dtype=np.float32),
            classes=np.empty((0,), dtype=np.uint8),
            ids=np.empty((0,), dtype=np.int64),
            lod=LodMetadata(
                requested_budget=budget,
                actual_count=0,
                decimation_method="none",
                complete=True,
                has_tombstones=False,
            ),
        )
        binary = encode_scene_binary(empty_scene)
        return Response(content=binary, media_type="application/octet-stream")

    adapter = open_target(target_uri)
    try:
        counts = adapter.counts()
        total_v = counts.total if counts.total is not None else 50000
        batch_limit = min(50000, total_v)
        batch = next(adapter.iter_live_vectors(batch_size=batch_limit))

        proj = project_to_3d([batch.vectors], n_components=3)
        n = len(proj.positions)

        classes = np.full(n, PointClass.HEALTHY.value, dtype=np.uint8)
        raw_scene = ScenePayload(
            positions=proj.positions,
            classes=classes,
            ids=batch.ids,
            lod=LodMetadata(
                requested_budget=budget,
                actual_count=n,
                decimation_method="none",
                complete=True,
                has_tombstones=False,
            ),
        )

        decimated_scene = decimate(raw_scene, budget=budget)
        binary = encode_scene_binary(decimated_scene)
        return Response(content=binary, media_type="application/octet-stream")
    finally:
        if hasattr(adapter, "close"):
            adapter.close()


@router.get("/metrics")
def get_metrics(request: Request) -> Response:
    """Prometheus OpenMetrics endpoint."""
    report_path = getattr(request.app.state, "report_path", None)
    target_uri = getattr(request.app.state, "target_uri", None)

    if target_uri:
        adapter = open_target(target_uri)
        try:
            config = load_config()
            report = run_audit(adapter, config)
            text = render_prometheus(report)
            return Response(content=text, media_type="text/plain; version=0.0.4")
        finally:
            if hasattr(adapter, "close"):
                adapter.close()

    if report_path and Path(report_path).exists():
        location = str(report_path)
        content = (
            "# HELP vhecfsck_verdict Overall audit verdict\n"
            "# TYPE vhecfsck_verdict gauge\n"
            f'vhecfsck_verdict{{target="{location}"}} 2\n'
        )
        return Response(content=content, media_type="text/plain; version=0.0.4")

    raise HTTPException(status_code=404, detail="No report or target configured")


@router.post("/api/audit")
def post_audit(request: Request) -> dict[str, str]:
    """Single-flight audit trigger endpoint."""
    if getattr(request.app.state, "audit_running", False):
        raise HTTPException(status_code=409, detail="Audit already in progress")

    target_uri = getattr(request.app.state, "target_uri", None)
    if not target_uri:
        msg = "No target URI configured for audit"
        raise HTTPException(status_code=400, detail=msg)

    try:
        request.app.state.audit_running = True
        adapter = open_target(target_uri)
        try:
            config = load_config()
            _ = run_audit(adapter, config)
        finally:
            if hasattr(adapter, "close"):
                adapter.close()
        return {"status": "completed"}
    finally:
        request.app.state.audit_running = False
