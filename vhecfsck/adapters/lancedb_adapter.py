"""LanceDB adapter placeholder — class resolvable without the SDK (P5)."""

from __future__ import annotations

import importlib

from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets


class LanceDBAdapter:
    """Structural stand-in until P5 implements the real read path."""

    def __init__(self, target: str) -> None:
        """Open a Lance dataset; requires the ``lancedb`` optional extra."""
        try:
            importlib.import_module("lancedb")
        except ImportError as exc:
            safe = redact_secrets(target)
            raise UsageError(
                f"LanceDB support is not installed (target={safe})",
                hint='pip install "vhecfsck[lancedb]"',
            ) from exc
        safe = redact_secrets(target)
        raise UsageError(
            f"LanceDB adapter is not implemented yet (target={safe})",
            hint="see roadmap ticket P5-01",
        )
