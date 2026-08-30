"""CLI entry point for vhecfsck commands (P3-04)."""

from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal

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
from vhecfsck.report import render_json, render_prometheus, render_terminal


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


class FormatChoice(str, Enum):
    """Output format choices for audit report."""

    TEXT = "text"
    JSON = "json"
    PROMETHEUS = "prometheus"


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
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Disable progress reporting to stderr.",
        ),
    ] = False,
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
            no_progress=no_progress,
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
    no_progress: bool,
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
    else:
        sys.stdout.write(rendered)
        sys.stdout.flush()

    # 9. Process exit code
    exit_code = verdict_to_exit_code(report.verdict)
    abort(exit_code)


def main() -> None:
    """Console-script and ``python -m vhecfsck`` entry point."""
    try:
        app()
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
    except Exception as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
