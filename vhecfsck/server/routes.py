"""API route definitions for the vhecfsck embedded web visualizer server.

P4-05 defined the surface; P6 added progressive scene chunks, the live progress
feed, the interactive probe, the charts panel and the camera presets.

These handlers are deliberately thin. Every number they return was computed in
``vhecfsck.core``; every policy decision they enforce lives in a framework-free
module next door, so it stays covered whether or not the ``server`` extra is
installed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket
from fastapi.websockets import WebSocketDisconnect

from vhecfsck.adapters.registry import open_target
from vhecfsck.config import load_config
from vhecfsck.core.lod import DEFAULT_DISPLAY_BUDGET, HARD_MAX_DISPLAY_BUDGET
from vhecfsck.core.scene_views import build_distribution_charts
from vhecfsck.models.report import report_to_dict
from vhecfsck.models.scene import DEFAULT_PALETTE_NAME, PALETTES
from vhecfsck.pipeline import run_audit
from vhecfsck.report.prometheus import render_prometheus
from vhecfsck.report.scene_codec import encode_scene_binary
from vhecfsck.server.probe_guard import (
    ProbeCache,
    ProbePolicy,
    ProbeRejected,
    RateLimiter,
    validate_probe_request,
)
from vhecfsck.server.probe_service import run_probe_bundle
from vhecfsck.server.progress import (
    ProgressTracker,
    event_to_dict,
    map_pipeline_stage,
)
from vhecfsck.server.scene_service import (
    AssembledScene,
    assemble_scene,
    findings_from_report,
    presets_payload,
)

router = APIRouter()

#: Seconds between progress frames pushed to a connected client.
PROGRESS_INTERVAL_SECONDS = 0.25

_IDLE_PROGRESS: dict[str, Any] = {
    "stage": "idle",
    "stage_index": 0,
    "stage_count": 0,
    "stage_fraction": 0.0,
    "fraction": 0.0,
    "elapsed_seconds": 0.0,
    "eta_seconds": None,
    "metrics": [],
    "detail": {},
    "terminal": False,
}


def _adapter_for(request: Request) -> Any:
    target_uri = getattr(request.app.state, "target_uri", None)
    if not target_uri:
        raise HTTPException(status_code=404, detail="No target URI configured")
    return open_target(target_uri)


def _close(adapter: Any) -> None:
    if hasattr(adapter, "close"):
        adapter.close()


def _probe_policy(request: Request) -> ProbePolicy:
    policy = getattr(request.app.state, "probe_policy", None)
    if policy is None:
        policy = ProbePolicy()
        request.app.state.probe_policy = policy
    return policy


def _probe_cache(request: Request) -> ProbeCache:
    cache = getattr(request.app.state, "probe_cache", None)
    if cache is None:
        cache = ProbeCache(max_size=_probe_policy(request).cache_size)
        request.app.state.probe_cache = cache
    return cache


def _rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "probe_limiter", None)
    if limiter is None:
        limiter = RateLimiter(policy=_probe_policy(request))
        request.app.state.probe_limiter = limiter
    return limiter


def _report_dict(request: Request) -> dict[str, Any] | None:
    cached = getattr(request.app.state, "last_report", None)
    if isinstance(cached, dict):
        if getattr(request.app.state, "progress_event", None) is None:
            _publish(request, ProgressTracker().finish())
        return cached
    report_path = getattr(request.app.state, "report_path", None)
    if report_path and Path(report_path).exists():
        text = Path(report_path).read_text(encoding="utf-8")
        loaded: dict[str, Any] = json.loads(text)
        request.app.state.last_report = loaded
        _publish(request, ProgressTracker().finish())
        return loaded
    return None


def _publish(request: Request, event: Any) -> dict[str, Any]:
    payload = event_to_dict(event)
    request.app.state.progress_event = payload
    return payload


def _idle_progress() -> dict[str, Any]:
    return dict(_IDLE_PROGRESS)


def _assembled_scene(
    request: Request,
    *,
    budget: int,
    device_max: int,
) -> AssembledScene:
    key = (budget, device_max)
    cache: dict[tuple[int, int], AssembledScene] = getattr(
        request.app.state, "assembled_scenes", {}
    )
    hit = cache.get(key)
    if hit is not None:
        return hit

    report = _report_dict(request)
    hubs, antis, _n_k = findings_from_report(report)
    adapter = _adapter_for(request)
    try:
        assembled = assemble_scene(
            adapter,
            requested_budget=budget,
            device_max_points=device_max,
            hub_ids=hubs,
            antihub_ids=antis,
        )
    finally:
        _close(adapter)

    cache = dict(cache)
    cache[key] = assembled
    request.app.state.assembled_scenes = cache
    return assembled


@router.get("/api/health")
def get_health(request: Request) -> dict[str, str]:
    """Liveness probe endpoint."""
    target = getattr(request.app.state, "target_uri", None) or ""
    return {"status": "ok", "target": target}


@router.get("/api/report")
def get_report(request: Request) -> dict[str, Any]:
    """Return JSON audit report data."""
    loaded = _report_dict(request)
    if loaded is not None:
        return loaded

    target_uri = getattr(request.app.state, "target_uri", None)
    if target_uri:
        adapter = open_target(target_uri)
        tracker = ProgressTracker()

        def _on_progress(stage: str, fraction: float) -> None:
            mapped = map_pipeline_stage(stage)
            if mapped:
                evt = tracker.advance(mapped, fraction)
                _publish(request, evt)

        try:
            report = run_audit(adapter, load_config(), on_progress=_on_progress)
            payload = report_to_dict(report)
            request.app.state.last_report = payload
            _publish(request, tracker.finish())
            return payload
        finally:
            _close(adapter)

    raise HTTPException(status_code=404, detail="No report or target URI configured")


@router.get("/api/scene")
def get_scene(
    request: Request,
    budget: int = Query(DEFAULT_DISPLAY_BUDGET, ge=10, le=HARD_MAX_DISPLAY_BUDGET),
    chunk: int = Query(0, ge=0),
    device_max: int = Query(HARD_MAX_DISPLAY_BUDGET, ge=10),
    palette: str = Query(DEFAULT_PALETTE_NAME),
) -> Response:
    """Return one progressive chunk of the binary 3D scene.

    Chunk 0 is the coarse pass and always carries every hub and anti-hub, so
    the findings paint before the background does.
    """
    if palette not in PALETTES:
        known = ", ".join(sorted(PALETTES))
        raise HTTPException(
            status_code=400, detail=f"unknown palette {palette!r}; known: {known}"
        )

    try:
        assembled = _assembled_scene(request, budget=budget, device_max=device_max)
        bundle = assembled.bundle(chunk)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {
        "X-Vhecfsck-Chunk": str(bundle.scene.lod.chunk_index),
        "X-Vhecfsck-Chunk-Count": str(bundle.scene.lod.chunk_count),
    }
    if bundle.budget_reason:
        headers["X-Vhecfsck-Budget-Refused"] = bundle.budget_reason

    return Response(
        content=encode_scene_binary(bundle.scene, palette=palette),
        media_type="application/octet-stream",
        headers=headers,
    )


@router.get("/api/charts")
def get_charts(request: Request) -> dict[str, Any]:
    """Return the bucketed distributions behind the charts panel."""
    report = _report_dict(request)
    _hubs, _antis, n_k = findings_from_report(report)
    try:
        assembled = _assembled_scene(
            request,
            budget=DEFAULT_DISPLAY_BUDGET,
            device_max=HARD_MAX_DISPLAY_BUDGET,
        )
        partition_sizes = assembled.partition_sizes
    except HTTPException:
        partition_sizes = None

    charts = build_distribution_charts(
        None if n_k is None else n_k,
        partition_sizes,
    )
    return {
        "nk_histogram": [dict(b) for b in charts.nk_histogram],
        "nk_log_y": charts.nk_log_y,
        "partition_histogram": (
            None
            if charts.partition_histogram is None
            else [dict(b) for b in charts.partition_histogram]
        ),
        "partition_mean": charts.partition_mean,
        "partition_unavailable_reason": charts.partition_unavailable_reason,
    }


@router.get("/api/presets")
def get_presets(request: Request) -> dict[str, Any]:
    """Return report-derived camera presets and the guided tour timeline."""
    assembled = _assembled_scene(
        request,
        budget=DEFAULT_DISPLAY_BUDGET,
        device_max=HARD_MAX_DISPLAY_BUDGET,
    )
    return presets_payload(assembled.full)


@router.post("/api/probe")
async def post_probe(request: Request) -> dict[str, Any]:
    """Probe one point: true neighbours, engine returns, misses, dead ids.

    Read-only and rate-limited. Arbitrary vector payloads are refused unless
    the operator explicitly enabled them.
    """
    policy = _probe_policy(request)
    client = request.client.host if request.client else "unknown"

    try:
        _rate_limiter(request).check(client)
        body = await request.json()
        probe_request = validate_probe_request(body, policy)
    except ProbeRejected as exc:
        headers = (
            {"Retry-After": str(int(exc.retry_after_seconds) + 1)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=exc.status_code, detail=exc.reason, headers=headers
        ) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="malformed JSON body") from exc

    cache = _probe_cache(request)
    cached = cache.get(probe_request.cache_key)
    if cached is not None:
        return dict(cached, cached=True)

    adapter = _adapter_for(request)
    try:
        payload = run_probe_bundle(
            adapter, query_id=probe_request.query_id, k=probe_request.k
        )
    finally:
        _close(adapter)

    if payload.get("available"):
        cache.put(probe_request.cache_key, payload)
    return dict(payload, cached=False)


@router.get("/api/progress")
def get_progress(request: Request) -> dict[str, Any]:
    """Latest progress frame, for clients whose proxy drops WebSockets."""
    event = getattr(request.app.state, "progress_event", None)
    if isinstance(event, dict):
        return event
    return _idle_progress()


@router.websocket("/api/progress")
async def progress_feed(websocket: WebSocket) -> None:
    """Stream per-stage audit progress, with metrics as each one resolves.

    The client falls back to polling ``GET /api/report`` (and
    ``GET /api/progress``) if this never opens; a proxy that drops WebSockets
    must not break the page.
    """
    await websocket.accept()
    last_sent: str | None = None
    try:
        while True:
            event = getattr(websocket.app.state, "progress_event", None)
            if isinstance(event, dict):
                serialised = json.dumps(event, sort_keys=True)
                if serialised != last_sent:
                    await websocket.send_json(event)
                    last_sent = serialised
                    if event.get("terminal"):
                        return
            await asyncio.sleep(PROGRESS_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


@router.get("/metrics")
def get_metrics(request: Request) -> Response:
    """Prometheus OpenMetrics endpoint."""
    report_path = getattr(request.app.state, "report_path", None)
    target_uri = getattr(request.app.state, "target_uri", None)

    if target_uri:
        adapter = open_target(target_uri)
        try:
            text = render_prometheus(run_audit(adapter, load_config()))
            return Response(content=text, media_type="text/plain; version=0.0.4")
        finally:
            _close(adapter)

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
        raise HTTPException(
            status_code=400, detail="No target URI configured for audit"
        )

    tracker = ProgressTracker()
    request.app.state.progress_tracker = tracker
    _publish(request, tracker.advance("descriptor", 0.0))

    try:
        request.app.state.audit_running = True
        adapter = open_target(target_uri)
        try:
            _publish(request, tracker.advance("descriptor", 1.0))
            _publish(request, tracker.advance("counts", 1.0))
            hubs, antis, _n_k = findings_from_report(_report_dict(request))
            assembled = assemble_scene(
                adapter,
                requested_budget=DEFAULT_DISPLAY_BUDGET,
                device_max_points=HARD_MAX_DISPLAY_BUDGET,
                hub_ids=hubs,
                antihub_ids=antis,
            )
            request.app.state.assembled_scenes = {
                (DEFAULT_DISPLAY_BUDGET, HARD_MAX_DISPLAY_BUDGET): assembled
            }
            _publish(request, tracker.advance("projection", 1.0))

            def _on_progress(stage: str, fraction: float) -> None:
                mapped = map_pipeline_stage(stage)
                if mapped is None:
                    return
                _publish(request, tracker.advance(mapped, fraction))

            def _on_metric(metric: Any) -> None:
                _publish(
                    request,
                    tracker.resolve_metric(
                        str(metric.id),
                        state=str(getattr(metric.state, "value", metric.state)),
                        value=metric.value,
                        unit=str(metric.unit or ""),
                    ),
                )

            report = run_audit(
                adapter,
                load_config(),
                on_progress=_on_progress,
                on_metric=_on_metric,
            )
            request.app.state.last_report = report_to_dict(report)
            # Re-assemble so hub ids from this report paint on the next fetch.
            hubs, antis, _n_k = findings_from_report(request.app.state.last_report)
            request.app.state.assembled_scenes = {
                (DEFAULT_DISPLAY_BUDGET, HARD_MAX_DISPLAY_BUDGET): assemble_scene(
                    adapter,
                    requested_budget=DEFAULT_DISPLAY_BUDGET,
                    device_max_points=HARD_MAX_DISPLAY_BUDGET,
                    hub_ids=hubs,
                    antihub_ids=antis,
                )
            }
        finally:
            _close(adapter)
        _publish(request, tracker.finish())
        return {"status": "completed"}
    finally:
        request.app.state.audit_running = False
        if not tracker.finished:
            _publish(request, tracker.finish())
