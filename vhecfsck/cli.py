"""CLI entry point. Commands are added by later tickets; this stub is installable."""

from __future__ import annotations

import typer

from vhecfsck.errors import VhecfsckError, abort, handle_uncaught

app = typer.Typer(
    name="vhecfsck",
    help="Topological audit and health diagnostics for vector indexes.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """vhecfsck root callback — subcommands land in later tickets."""


def main() -> None:
    """Console-script and ``python -m vhecfsck`` entry point."""
    try:
        app()
    except VhecfsckError as exc:
        abort(handle_uncaught(exc))
    except Exception as exc:
        abort(handle_uncaught(exc))
