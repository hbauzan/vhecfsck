"""Admission control and caching for the interactive probe endpoint (P6-03).

Framework-free so it can be tested without the ``server`` extra.

The endpoint is loopback-only, but the process behind it holds a read
connection to somebody's production index. Two defaults follow from that:
arbitrary vector payloads are refused unless explicitly enabled, and the rate
limiter is on by default rather than opt-in. A probe is a `Q=1` exact pass over
the whole corpus; unmetered, it is a denial-of-service primitive pointed at the
database the tool was invited to read.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

#: Neighbours a probe may request. The upper bound keeps one click from
#: dragging back a meaningful slice of the corpus.
MIN_K = 1
MAX_K = 100
DEFAULT_K = 10


class ProbeRejected(Exception):  # noqa: N818 — admission refusal, not an internal error
    """A probe request was refused before any corpus work happened.

    Attributes:
        reason: Human-readable explanation, safe to return to the client.
        status_code: Suggested HTTP status for the refusal.
        retry_after_seconds: When the client may retry, if applicable.
    """

    def __init__(
        self,
        reason: str,
        *,
        status_code: int = 400,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Store the refusal so the route can render it verbatim."""
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ProbePolicy:
    """Admission rules for the probe endpoint.

    Attributes:
        allow_vector_payload: When False, a request may only name a corpus id.
        max_requests: Requests permitted per client per window.
        window_seconds: Length of the sliding rate-limit window.
        cache_size: Probe results retained per session.
        max_k: Largest neighbourhood a caller may request.
    """

    allow_vector_payload: bool = False
    max_requests: int = 30
    window_seconds: float = 60.0
    cache_size: int = 256
    max_k: int = MAX_K


@dataclass(frozen=True)
class ProbeRequest:
    """A validated probe request.

    Attributes:
        query_id: Corpus id to probe.
        k: Neighbours to compare.
    """

    query_id: int
    k: int

    @property
    def cache_key(self) -> tuple[int, int]:
        """Key identifying this probe within a session cache."""
        return (self.query_id, self.k)


def validate_probe_request(
    payload: Mapping[str, Any],
    policy: ProbePolicy,
) -> ProbeRequest:
    """Parse and admit a probe request body.

    Args:
        payload: Decoded JSON request body.
        policy: Rules to apply.

    Returns:
        The validated request.

    Raises:
        ProbeRejected: If the body names a vector while vector payloads are
            disabled, omits ``id``, or asks for an out-of-range ``k``.
    """
    if not policy.allow_vector_payload:
        for key in ("vector", "query_vector", "embedding"):
            if key in payload:
                raise ProbeRejected(
                    "this server accepts probes by corpus id only; sending an "
                    "arbitrary vector is disabled",
                    status_code=403,
                )

    if "id" not in payload:
        raise ProbeRejected("probe request must name a corpus id as 'id'")

    raw_id = payload["id"]
    if isinstance(raw_id, bool) or not isinstance(raw_id, int):
        raise ProbeRejected("'id' must be an integer corpus id")

    raw_k = payload.get("k", DEFAULT_K)
    if isinstance(raw_k, bool) or not isinstance(raw_k, int):
        raise ProbeRejected("'k' must be an integer")
    if raw_k < MIN_K or raw_k > policy.max_k:
        raise ProbeRejected(
            f"'k' must be between {MIN_K} and {policy.max_k}, got {raw_k}"
        )

    return ProbeRequest(query_id=int(raw_id), k=int(raw_k))


@dataclass
class RateLimiter:
    """Sliding-window rate limiter keyed by client.

    Attributes:
        policy: Limits to enforce.
        clock: Monotonic time source; injected so tests need no sleeping.
    """

    policy: ProbePolicy = field(default_factory=ProbePolicy)
    clock: Callable[[], float] = time.monotonic
    _hits: dict[str, deque[float]] = field(default_factory=dict, init=False)

    def check(self, client: str) -> None:
        """Admit one request from ``client``, or refuse it.

        Args:
            client: Stable client identifier, e.g. a peer address.

        Raises:
            ProbeRejected: With status 429 when the window is full.
        """
        now = self.clock()
        window = self._hits.setdefault(client, deque())
        cutoff = now - self.policy.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= self.policy.max_requests:
            retry_after = max(0.0, window[0] + self.policy.window_seconds - now)
            raise ProbeRejected(
                f"probe rate limit reached: {self.policy.max_requests} requests "
                f"per {self.policy.window_seconds:g}s",
                status_code=429,
                retry_after_seconds=retry_after,
            )

        window.append(now)

    def remaining(self, client: str) -> int:
        """Requests ``client`` may still make in the current window.

        Args:
            client: Client identifier.

        Returns:
            Remaining allowance, never negative.
        """
        now = self.clock()
        window = self._hits.get(client)
        if window is None:
            return self.policy.max_requests
        cutoff = now - self.policy.window_seconds
        live = sum(1 for t in window if t > cutoff)
        return max(0, self.policy.max_requests - live)


@dataclass
class ProbeCache:
    """Session-scoped LRU cache of probe results, keyed by point and ``k``.

    A single-query exact pass is a few seconds on a million vectors; repeating
    it because the operator clicked the same hub twice is pure waste.

    Attributes:
        max_size: Entries retained before the least-recently-used is evicted.
    """

    max_size: int = 256
    _entries: OrderedDict[tuple[int, int], Any] = field(
        default_factory=OrderedDict, init=False
    )
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    def get(self, key: tuple[int, int]) -> Any | None:
        """Look up a cached probe result.

        Args:
            key: ``(query_id, k)``.

        Returns:
            The cached result, or None on a miss.
        """
        if key in self._entries:
            self._entries.move_to_end(key)
            self.hits += 1
            return self._entries[key]
        self.misses += 1
        return None

    def put(self, key: tuple[int, int], value: Any) -> None:
        """Store a probe result, evicting the least-recently-used entry.

        Args:
            key: ``(query_id, k)``.
            value: Result to retain.
        """
        if self.max_size <= 0:
            return
        if key in self._entries:
            self._entries.move_to_end(key)
        self._entries[key] = value
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)

    def invalidate(self, query_id: int) -> int:
        """Drop every cached entry for one point.

        Args:
            query_id: Point whose results are stale.

        Returns:
            Number of entries removed.
        """
        stale = [key for key in self._entries if key[0] == query_id]
        for key in stale:
            del self._entries[key]
        return len(stale)

    def __len__(self) -> int:
        """Entries currently retained."""
        return len(self._entries)
