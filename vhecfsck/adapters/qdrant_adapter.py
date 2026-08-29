"""Qdrant adapter placeholder — class resolvable without the SDK (P7)."""

from __future__ import annotations

import importlib

from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets


class QdrantAdapter:
    """Structural stand-in until P7 implements the real read path."""

    def __init__(self, target: str) -> None:
        """Connect to a Qdrant collection; requires the ``qdrant`` optional extra."""
        try:
            importlib.import_module("qdrant_client")
        except ImportError as exc:
            safe = redact_secrets(target)
            raise UsageError(
                f"Qdrant support is not installed (target={safe})",
                hint='pip install "vhecfsck[qdrant]"',
            ) from exc
        safe = redact_secrets(target)
        raise UsageError(
            f"Qdrant adapter is not implemented yet (target={safe})",
            hint="see roadmap ticket P7-01",
        )
