"""CLI entry point. Commands are added by later tickets; this stub is installable."""

from __future__ import annotations

from typing import Annotated, Literal

import typer

from vhecfsck.errors import VhecfsckError, abort, handle_uncaught
from vhecfsck.logging import configure_logging

app = typer.Typer(
    name="vhecfsck",
    help="Topological audit and health diagnostics for vector indexes.",
    add_completion=False,
    no_args_is_help=True,
)

_DEBUG = False


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
    """vhecfsck root callback — subcommands land in later tickets."""
    global _DEBUG
    _DEBUG = debug
    verbosity = -1 if quiet else min(verbose, 2)
    configure_logging(verbosity=verbosity, log_format=log_format)


def main() -> None:
    """Console-script and ``python -m vhecfsck`` entry point."""
    try:
        app()
    except VhecfsckError as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
    except Exception as exc:
        abort(handle_uncaught(exc, debug=_DEBUG))
