"""CLI entry point for vhecfsck commands (P3-04 / P3-05 / P3-07)."""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import click
import click.exceptions
import typer

from vhecfsck.adapters.base import SearchParams
from vhecfsck.adapters.registry import open_target
from vhecfsck.config import _METRIC_IDS, load_config
from vhecfsck.core.verdict import verdict_to_exit_code
from vhecfsck.errors import ExitCode, UsageError, VhecfsckError, abort, handle_uncaught
from vhecfsck.logging import configure_logging
from vhecfsck.pipeline import ProgressCallback, run_audit
from vhecfsck.report import (
    render_json,
    render_markdown,
    render_prometheus,
    render_terminal,
)


# Ensure all Click UsageErrors (invalid flags, missing options) exit with exit code 4.
def _patch_usage_error(mod: Any) -> None:
    if not hasattr(mod, "UsageError"):
        return
    orig_init = mod.UsageError.__init__

    def _usage_error_init(self: Any, message: str, ctx: Any = None) -> None:
        orig_init(self, message, ctx=ctx)
        self.exit_code = int(ExitCode.USAGE)

    mod.UsageError.__init__ = _usage_error_init


_patch_usage_error(click.exceptions)
try:
    import typer._click.exceptions

    _patch_usage_error(typer._click.exceptions)
except ImportError:
    pass

app = typer.Typer(
    name="vhecfsck",
    help="Topological audit and health diagnostics for vector indexes.",
    add_completion=False,
    no_args_is_help=True,
)

_DEBUG = False
_QUIET = False


def parse_filter_option(raw: str) -> tuple[str, str]:
    """Parse ``--filter field=value`` into a payload equality clause."""
    if "=" not in raw:
        raise UsageError(
            f"invalid --filter {raw!r}",
            hint="Expected field=value, e.g. --filter tenant_id=t0",
        )
    key, _, value = raw.partition("=")
    key, value = key.strip(), value.strip()
    if not key or not value:
        raise UsageError(
            f"invalid --filter {raw!r}",
            hint="Expected field=value, e.g. --filter tenant_id=t0",
        )
    return key, value


class FormatChoice(str, Enum):
    """Output format choices for audit report."""

    TEXT = "text"
    JSON = "json"
    PROMETHEUS = "prometheus"


class ExportFormatChoice(str, Enum):
    """Output format choices for export report command."""

    TEXT = "text"
    JSON = "json"
    PROMETHEUS = "prometheus"
    MARKDOWN = "markdown"


class DemoSizeChoice(str, Enum):
    """Corpus scale size choice for demo command."""

    SMALL = "small"
    LARGE = "large"
    TINY = "tiny"


@app.callback()
def _root(
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Raise log verbosity."),
    ] = 0,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Only errors to stderr."),
    ] = False,
    log_format: Annotated[
        Literal["human", "json"],
        typer.Option("--log-format", help="Diagnostic log format (stderr)."),
    ] = "human",
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show tracebacks on internal errors."),
    ] = False,
) -> None:
    """vhecfsck root callback."""
    global _DEBUG, _QUIET
    _DEBUG = debug
    _QUIET = quiet
    verbosity = -1 if quiet else min(verbose, 2)
    configure_logging(verbosity=verbosity, log_format=log_format)
    if os.environ.get("_VHECFSCK_FAULT_INJECT") == "1":
        raise RuntimeError("Fault injected for exit code 70 test")


@app.command(name="audit")
def audit(
    target_opt: Annotated[
        str | None,
        typer.Option(
            "--target",
            "-t",
            help="Target index URI or path.",
        ),
    ] = None,
    target_pos: Annotated[
        str | None,
        typer.Argument(
            help="Target index URI or path.",
        ),
    ] = None,
    format: Annotated[
        FormatChoice,
        typer.Option(
            "--format",
            help="Report output format: text, json, or prometheus.",
        ),
    ] = FormatChoice.TEXT,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (defaults to stdout).",
        ),
    ] = None,
    queries: Annotated[
        int | None,
        typer.Option(
            "--queries",
            help="Number of queries to sample.",
        ),
    ] = None,
    queries_count: Annotated[
        int | None,
        typer.Option(
            "--queries-count",
            help="Number of queries to sample.",
        ),
    ] = None,
    k: Annotated[
        int | None,
        typer.Option(
            "--k",
            help="k nearest neighbors for canary recall.",
        ),
    ] = None,
    hubness_sample: Annotated[
        int | None,
        typer.Option(
            "--hubness-sample",
            help="Sample size for hubness metric.",
        ),
    ] = None,
    k_hub: Annotated[
        int | None,
        typer.Option(
            "--k-hub",
            help="k nearest neighbors for hubness.",
        ),
    ] = None,
    hubness_source: Annotated[
        str | None,
        typer.Option(
            "--hubness-source",
            help="Hubness reference source: 'truth' or 'engine'.",
        ),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option(
            "--seed",
            help="Random seed for query sampling.",
        ),
    ] = None,
    nprobe: Annotated[
        int | None,
        typer.Option(
            "--nprobe",
            help="IVF nprobe search parameter.",
        ),
    ] = None,
    ef_search: Annotated[
        int | None,
        typer.Option(
            "--ef-search",
            help="HNSW ef_search parameter.",
        ),
    ] = None,
    max_seconds: Annotated[
        float | None,
        typer.Option(
            "--max-seconds",
            help="Maximum wall-clock limit in seconds.",
        ),
    ] = None,
    max_memory_mb: Annotated[
        float | None,
        typer.Option(
            "--max-memory-mb",
            help="Maximum memory budget in MB.",
        ),
    ] = None,
    strict_unavailable: Annotated[
        bool | None,
        typer.Option(
            "--strict-unavailable/--no-strict-unavailable",
            help="Treat UNAVAILABLE metrics as FAIL.",
        ),
    ] = None,
    only: Annotated[
        str | None,
        typer.Option(
            "--only",
            help="Comma-separated metric IDs to include.",
        ),
    ] = None,
    skip: Annotated[
        str | None,
        typer.Option(
            "--skip",
            help="Comma-separated metric IDs to skip.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to custom audit configuration file.",
        ),
    ] = None,
    dataset_version: Annotated[
        int | None,
        typer.Option(
            "--dataset-version",
            help="Dataset version/snapshot to pin for LanceDB.",
        ),
    ] = None,
    column: Annotated[
        str | None,
        typer.Option(
            "--column",
            help="Vector column name for multi-vector datasets.",
        ),
    ] = None,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Disable progress reporting to stderr.",
        ),
    ] = False,
    filter_clause: Annotated[
        str | None,
        typer.Option(
            "--filter",
            help="Restrict canary recall to payload equality (field=value).",
        ),
    ] = None,
    group_by: Annotated[
        str | None,
        typer.Option(
            "--group-by",
            help="Per-group canary breakdown on a payload field.",
        ),
    ] = None,
) -> None:
    """Perform a topological health audit on a vector index target."""
    try:
        _audit_impl(
            target_opt=target_opt,
            target_pos=target_pos,
            format=format,
            output=output,
            queries=queries,
            queries_count=queries_count,
            k=k,
            hubness_sample=hubness_sample,
            k_hub=k_hub,
            hubness_source=hubness_source,
            seed=seed,
            nprobe=nprobe,
            ef_search=ef_search,
            max_seconds=max_seconds,
            max_memory_mb=max_memory_mb,
            strict_unavailable=strict_unavailable,
            only=only,
            skip=skip,
            config=config,
            dataset_version=dataset_version,
            column=column,
            no_progress=no_progress,
            filter_clause=filter_clause,
            group_by=group_by,
        )
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))


def _audit_impl(
    target_opt: str | None,
    target_pos: str | None,
    format: FormatChoice,
    output: Path | None,
    queries: int | None,
    queries_count: int | None,
    k: int | None,
    hubness_sample: int | None,
    k_hub: int | None,
    hubness_source: str | None,
    seed: int | None,
    nprobe: int | None,
    ef_search: int | None,
    max_seconds: float | None,
    max_memory_mb: float | None,
    strict_unavailable: bool | None,
    only: str | None,
    skip: str | None,
    config: Path | None,
    dataset_version: int | None,
    column: str | None,
    no_progress: bool,
    filter_clause: str | None = None,
    group_by: str | None = None,
) -> None:
    raw_target = target_opt or target_pos
    if not raw_target:
        raise UsageError(
            "target index URI or path is required",
            hint=(
                "Specify --target <uri> (e.g. synthetic://healthy or "
                "lance:///path/data.lance)."
            ),
        )

    if dataset_version is not None or column is not None:
        sep = "&" if "?" in raw_target else "?"
        params = []
        if dataset_version is not None:
            params.append(f"dataset_version={dataset_version}")
        if column is not None:
            params.append(f"column={column}")
        raw_target = f"{raw_target}{sep}{'&'.join(params)}"

    # 1. Handle metric selection (--only / --skip)
    metrics_enabled: dict[str, bool] | None = None
    if only is not None and skip is not None:
        raise UsageError(
            "cannot specify both --only and --skip",
            hint="Use --only to select specific metrics OR --skip to exclude metrics.",
        )

    if only is not None:
        selected = [m.strip() for m in only.split(",") if m.strip()]
        for mid in selected:
            if mid not in _METRIC_IDS:
                raise UsageError(
                    f"unknown metric '{mid}' in --only",
                    hint=f"Known metrics: {', '.join(_METRIC_IDS)}",
                )
        metrics_enabled = {mid: (mid in selected) for mid in _METRIC_IDS}
    elif skip is not None:
        skipped = [m.strip() for m in skip.split(",") if m.strip()]
        for mid in skipped:
            if mid not in _METRIC_IDS:
                raise UsageError(
                    f"unknown metric '{mid}' in --skip",
                    hint=f"Known metrics: {', '.join(_METRIC_IDS)}",
                )
        metrics_enabled = {mid: (mid not in skipped) for mid in _METRIC_IDS}

    # 2. Build CLI config overrides
    cli_overrides: dict[str, Any] = {}
    if seed is not None:
        cli_overrides["seed"] = seed
    num_queries = queries_count if queries_count is not None else queries
    if num_queries is not None:
        cli_overrides["queries"] = num_queries
    if k is not None:
        cli_overrides["k"] = k
    if hubness_sample is not None:
        cli_overrides["hubness_sample_size"] = hubness_sample
    if k_hub is not None:
        cli_overrides["k_hub"] = k_hub
    if hubness_source is not None:
        if hubness_source not in {"truth", "engine"}:
            raise UsageError(
                f"invalid --hubness-source {hubness_source!r}",
                hint="Use 'truth' or 'engine'.",
            )
        cli_overrides["hubness_source"] = hubness_source
    if max_seconds is not None:
        cli_overrides["max_seconds"] = max_seconds
    if max_memory_mb is not None:
        cli_overrides["max_memory_mb"] = max_memory_mb
    if strict_unavailable is not None:
        cli_overrides["strict_unavailable"] = strict_unavailable
    if metrics_enabled is not None:
        cli_overrides["metrics_enabled"] = metrics_enabled
    if group_by is not None:
        cli_overrides["group_by"] = group_by.strip()
    if filter_clause is not None:
        field, value = parse_filter_option(filter_clause)
        cli_overrides["filter_field"] = field
        cli_overrides["filter_value"] = value
    if group_by is not None and filter_clause is not None:
        raise UsageError(
            "cannot combine --filter and --group-by",
            hint=(
                "Use --filter for one payload equality, or --group-by for a breakdown."
            ),
        )

    effective_config = load_config(config_path=config, cli_overrides=cli_overrides)

    # 3. Build search params
    search_params: SearchParams = {}
    if nprobe is not None:
        search_params["nprobe"] = nprobe
    if ef_search is not None:
        search_params["ef_search"] = ef_search

    # 4. Open adapter
    adapter = open_target(raw_target)

    # 5. Progress callback
    on_progress: ProgressCallback | None = None
    if (
        not no_progress
        and not _QUIET
        and format != FormatChoice.JSON
        and sys.stderr.isatty()
    ):

        def _on_progress(stage: str, fraction: float) -> None:
            pct = int(fraction * 100)
            sys.stderr.write(f"\r[audit] {stage}: {pct}%")
            if fraction >= 1.0 or stage == "done":
                sys.stderr.write("\n")
            sys.stderr.flush()

        on_progress = _on_progress

    # 6. Run audit
    report = run_audit(
        adapter,
        effective_config,
        search_params=search_params if search_params else None,
        on_progress=on_progress,
    )

    # 7. Render output
    if format == FormatChoice.JSON:
        rendered = render_json(report)
    elif format == FormatChoice.PROMETHEUS:
        rendered = render_prometheus(report)
    else:
        use_color = (
            sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
        rendered = render_terminal(report, color=use_color)

    # 8. Output report
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    elif not _QUIET:
        sys.stdout.write(rendered)
        sys.stdout.flush()

    # 9. Process exit code
    exit_code = verdict_to_exit_code(report.verdict)
    abort(exit_code)


@app.command(name="demo")
def demo(
    scenario: Annotated[
        str,
        typer.Option(
            "--scenario",
            help="Synthetic scenario name (e.g. tombstoned, healthy, drifted).",
        ),
    ] = "tombstoned",
    size: Annotated[
        DemoSizeChoice,
        typer.Option(
            "--size",
            help="Corpus scale size (small, large, or tiny).",
        ),
    ] = DemoSizeChoice.SMALL,
    serve: Annotated[
        bool,
        typer.Option(
            "--serve",
            help="Hand off run to 3D scene visualizer server.",
        ),
    ] = False,
    format: Annotated[
        FormatChoice,
        typer.Option(
            "--format",
            help="Report output format: text, json, or prometheus.",
        ),
    ] = FormatChoice.TEXT,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (defaults to stdout).",
        ),
    ] = None,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Disable progress reporting to stderr.",
        ),
    ] = False,
) -> None:
    """Run a 60-second zero-dependency synthetic index demonstration audit."""
    try:
        _demo_impl(
            scenario=scenario,
            size=size.value,
            serve=serve,
            format=format,
            output=output,
            no_progress=no_progress,
        )
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))


def _demo_impl(
    scenario: str,
    size: str,
    serve: bool,
    format: FormatChoice,
    output: Path | None,
    no_progress: bool,
) -> None:
    from vhecfsck.adapters.scenarios import open_scenario
    from vhecfsck.synthetic.scenarios import SCENARIO_NAMES

    raw_scenario = scenario.strip().lower()
    if raw_scenario not in SCENARIO_NAMES:
        raise UsageError(
            f"unknown synthetic scenario {scenario!r}",
            hint=f"Supported scenarios: {', '.join(SCENARIO_NAMES)}",
        )

    opened = open_scenario(raw_scenario, size=size)  # type: ignore[arg-type]
    adapter = opened.adapter
    spec = opened.spec

    if format != FormatChoice.JSON and not _QUIET:
        sys.stderr.write(f"[demo] Reproducing real-world issue: {spec.issue}\n")
        sys.stderr.flush()

    effective_config = load_config(cli_overrides={"seed": spec.build_seed})
    search_params = cast(
        "SearchParams | None",
        dict(spec.default_search_params) if spec.default_search_params else None,
    )

    on_progress: ProgressCallback | None = None
    if (
        not no_progress
        and not _QUIET
        and format != FormatChoice.JSON
        and sys.stderr.isatty()
    ):

        def _on_progress(stage: str, fraction: float) -> None:
            pct = int(fraction * 100)
            sys.stderr.write(f"\r[audit] {stage}: {pct}%")
            if fraction >= 1.0 or stage == "done":
                sys.stderr.write("\n")
            sys.stderr.flush()

        on_progress = _on_progress

    try:
        report = run_audit(
            adapter,
            effective_config,
            search_params=search_params,
            on_progress=on_progress,
        )
    finally:
        adapter.close()

    if format == FormatChoice.JSON:
        rendered = render_json(report)
    elif format == FormatChoice.PROMETHEUS:
        rendered = render_prometheus(report)
    else:
        use_color = (
            sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
        rendered = render_terminal(report, color=use_color)

    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    elif not _QUIET:
        sys.stdout.write(rendered)
        sys.stdout.flush()

    if serve and not _QUIET:
        sys.stderr.write(
            "[demo] Note: --serve 3D visualizer server requires P4 (vhecfsck serve).\n"
        )
        sys.stderr.flush()

    exit_code = verdict_to_exit_code(report.verdict)
    abort(exit_code)


@app.command(name="export")
def export(
    report_path: Annotated[
        Path,
        typer.Option(
            "--report",
            "-r",
            help="Path to input JSON report file.",
        ),
    ],
    format: Annotated[
        ExportFormatChoice,
        typer.Option(
            "--format",
            help="Report output format: text, json, prometheus, or markdown.",
        ),
    ] = ExportFormatChoice.TEXT,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (defaults to stdout).",
        ),
    ] = None,
) -> None:
    """Re-render a stored audit report JSON in another format."""
    try:
        _export_impl(
            report_path=report_path,
            format=format,
            output=output,
        )
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))


def _export_impl(
    report_path: Path,
    format: ExportFormatChoice,
    output: Path | None,
) -> None:
    import json

    from vhecfsck.models.report import Report

    if not report_path.exists():
        raise UsageError(
            f"report file not found: {report_path}",
            hint="Specify a valid path to an existing JSON report file.",
        )

    try:
        raw_text = report_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        raise UsageError(
            f"failed to parse JSON from {report_path}: {exc}",
            hint="Ensure file is valid UTF-8 JSON.",
        ) from exc

    version_str = str(data.get("schema_version", "1.0"))
    try:
        major = int(version_str.split(".")[0])
    except ValueError:
        major = 1

    if major > 1:
        raise UsageError(
            f"unsupported report schema_version {version_str!r}",
            hint="This version of vhecfsck supports schema_version 1.x",
        )

    try:
        report = Report.model_validate(data)
    except Exception as exc:
        raise UsageError(
            f"invalid report structure in {report_path}: {exc}",
            hint="Ensure report conforms to vhecfsck Report schema.",
        ) from exc

    if format == ExportFormatChoice.JSON:
        rendered = render_json(report)
    elif format == ExportFormatChoice.PROMETHEUS:
        rendered = render_prometheus(report)
    elif format == ExportFormatChoice.MARKDOWN:
        rendered = render_markdown(report)
    else:
        use_color = (
            sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM") != "dumb"
        )
        rendered = render_terminal(report, color=use_color)

    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    elif not _QUIET:
        sys.stdout.write(rendered)
        sys.stdout.flush()

    exit_code = verdict_to_exit_code(report.verdict)
    abort(exit_code)


@app.command(name="serve")
def serve(
    target: Annotated[
        str,
        typer.Option(
            "--target",
            "-t",
            help="Target vector index URI.",
        ),
    ] = "",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Server HTTP port.",
        ),
    ] = 8765,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Bind host address.",
        ),
    ] = "127.0.0.1",
    no_browser: Annotated[
        bool,
        typer.Option(
            "--no-browser",
            help="Do not automatically open web browser.",
        ),
    ] = False,
    report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="Path to pre-computed JSON report file.",
        ),
    ] = None,
) -> None:
    """Launch embedded HTTP/WebSocket server for 3D visualizer."""
    try:
        _serve_impl(
            target=target,
            port=port,
            host=host,
            no_browser=no_browser,
            report_path=report,
        )
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))


def _serve_impl(
    target: str,
    port: int,
    host: str,
    no_browser: bool,
    report_path: Path | None,
) -> None:
    _ = no_browser
    from vhecfsck.server.app import check_server_dependencies, create_app

    check_server_dependencies()

    if host == "0.0.0.0" and not _QUIET:
        warn_msg = (
            "Warning: binding vhecfsck server to 0.0.0.0 "
            "exposes database read access without auth\n"
        )
        sys.stderr.write(warn_msg)
        sys.stderr.flush()

    report_str = str(report_path) if report_path else None
    app_instance = create_app(target_uri=target or None, report_path=report_str)

    import uvicorn

    log_lvl = "info" if not _QUIET else "error"
    uvicorn.run(app_instance, host=host, port=port, log_level=log_lvl)


def main() -> None:
    """Console-script and ``python -m vhecfsck`` entry point."""
    try:
        app()
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
    except Exception as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
