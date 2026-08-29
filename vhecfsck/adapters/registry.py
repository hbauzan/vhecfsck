"""Target URI → adapter resolution (registration table, no if/elif chain).

Schemes: ``synthetic://``, ``lance://`` (and bare ``*.lance`` paths),
``qdrant://``, ``postgres://``. Engine SDKs load only inside openers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from vhecfsck.adapters.base import IndexAdapter
from vhecfsck.adapters.lancedb_adapter import LanceDBAdapter
from vhecfsck.adapters.postgres_adapter import PostgresAdapter
from vhecfsck.adapters.qdrant_adapter import QdrantAdapter
from vhecfsck.adapters.synthetic_adapter import SyntheticAdapter
from vhecfsck.errors import UsageError
from vhecfsck.logging import redact_secrets
from vhecfsck.models import MetricSpace
from vhecfsck.synthetic.generator import generate_corpus
from vhecfsck.synthetic.pathologies import corpus_state_from_generated

Opener = Callable[[str], IndexAdapter]

SUPPORTED_SCHEMES: tuple[str, ...] = (
    "synthetic",
    "lance",
    "qdrant",
    "postgres",
)


@dataclass(frozen=True)
class _Entry:
    adapter_class: type
    opener: Opener


_ENTRIES: dict[str, _Entry] = {}


def register(
    scheme: str,
    *,
    adapter_class: type,
    opener: Opener,
) -> None:
    """Register (or replace) a scheme → adapter mapping."""
    key = scheme.lower().strip()
    if not key:
        msg = "scheme must be non-empty"
        raise UsageError(msg)
    _ENTRIES[key] = _Entry(adapter_class=adapter_class, opener=opener)


def registered_schemes() -> tuple[str, ...]:
    """Schemes currently registered (sorted for stable messages)."""
    return tuple(sorted(_ENTRIES))


def resolve_class(target: str) -> type:
    """Return the adapter class for ``target`` without importing engine SDKs."""
    scheme, _ = _split_target(target)
    entry = _ENTRIES.get(scheme)
    if entry is None:
        raise _unknown_scheme(scheme, target)
    return entry.adapter_class


def open_target(target: str) -> IndexAdapter:
    """Resolve ``target`` and open a read-only adapter instance."""
    scheme, _ = _split_target(target)
    entry = _ENTRIES.get(scheme)
    if entry is None:
        raise _unknown_scheme(scheme, target)
    try:
        return entry.opener(target)
    except UsageError as exc:
        raise UsageError(
            redact_secrets(str(exc)),
            hint=redact_secrets(exc.hint),
        ) from None
    except Exception as exc:
        safe = redact_secrets(target)
        raise UsageError(
            f"failed to open target {safe}: {redact_secrets(str(exc))}",
            hint="check the URI and optional extras",
        ) from None


def _unknown_scheme(scheme: str, target: str) -> UsageError:
    supported = ", ".join(registered_schemes()) or ", ".join(SUPPORTED_SCHEMES)
    safe = redact_secrets(target)
    return UsageError(
        f"unknown target scheme {scheme!r} (target={safe}); "
        f"supported schemes: {supported}",
        hint="example: synthetic://tiny, lance:///path/data.lance",
    )


def _split_target(target: str) -> tuple[str, str]:
    raw = target.strip()
    if not raw:
        raise UsageError("target must be non-empty", hint="pass --target URI")
    if "://" in raw:
        scheme, _, rest = raw.partition("://")
        return scheme.lower(), rest
    # Bare filesystem path with .lance suffix → lance
    path = Path(raw)
    if path.suffix == ".lance" or raw.endswith(".lance"):
        return "lance", raw
    safe = redact_secrets(raw)
    raise UsageError(
        f"cannot infer scheme for target {safe}",
        hint=f"supported schemes: {', '.join(SUPPORTED_SCHEMES)}",
    )


def _open_synthetic(target: str) -> IndexAdapter:
    parsed = urlparse(target if "://" in target else f"synthetic://{target}")
    name = (parsed.netloc or parsed.path or "default").strip("/")
    if not name:
        name = "default"
    # Deterministic tiny corpus until named scenarios land (P1-08).
    digest = blake2b(name.encode("utf-8"), digest_size=4).digest()
    seed = int.from_bytes(digest, "big") % (2**31 - 1)
    gen = generate_corpus(
        64,
        8,
        n_clusters=4,
        cluster_std=0.2,
        cluster_size_skew=0.0,
        seed=seed,
        metric_space=MetricSpace.L2,
    )
    state = corpus_state_from_generated(gen)
    location = redact_secrets(target)
    return SyntheticAdapter(
        state,
        mode="exact",
        index_name=name,
        location=location,
    )


def _open_lance(target: str) -> IndexAdapter:
    return cast(IndexAdapter, LanceDBAdapter(target))


def _open_qdrant(target: str) -> IndexAdapter:
    return cast(IndexAdapter, QdrantAdapter(target))


def _open_postgres(target: str) -> IndexAdapter:
    return cast(IndexAdapter, PostgresAdapter(target))


def _register_builtins() -> None:
    if _ENTRIES:
        return
    register("synthetic", adapter_class=SyntheticAdapter, opener=_open_synthetic)
    register("lance", adapter_class=LanceDBAdapter, opener=_open_lance)
    register("qdrant", adapter_class=QdrantAdapter, opener=_open_qdrant)
    register("postgres", adapter_class=PostgresAdapter, opener=_open_postgres)


_register_builtins()
