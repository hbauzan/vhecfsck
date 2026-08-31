"""Unit tests for probe admission control and caching (P6-03)."""

from __future__ import annotations

import pytest
from vhecfsck.server.probe_guard import (
    DEFAULT_K,
    MAX_K,
    ProbeCache,
    ProbePolicy,
    ProbeRejected,
    RateLimiter,
    validate_probe_request,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


# --- request validation ------------------------------------------------------


def test_a_probe_by_corpus_id_is_admitted() -> None:
    request = validate_probe_request({"id": 42, "k": 8}, ProbePolicy())

    assert request.query_id == 42
    assert request.k == 8
    assert request.cache_key == (42, 8)


def test_k_defaults_when_omitted() -> None:
    assert validate_probe_request({"id": 1}, ProbePolicy()).k == DEFAULT_K


def test_an_arbitrary_vector_payload_is_refused_by_default() -> None:
    """Loopback or not, this process holds a production read connection."""
    for key in ("vector", "query_vector", "embedding"):
        with pytest.raises(ProbeRejected) as excinfo:
            validate_probe_request({"id": 1, key: [0.1, 0.2]}, ProbePolicy())
        assert excinfo.value.status_code == 403


def test_an_arbitrary_vector_payload_is_admitted_when_explicitly_enabled() -> None:
    policy = ProbePolicy(allow_vector_payload=True)

    request = validate_probe_request({"id": 1, "vector": [0.1]}, policy)

    assert request.query_id == 1


def test_a_request_without_an_id_is_refused() -> None:
    with pytest.raises(ProbeRejected, match="corpus id"):
        validate_probe_request({"k": 5}, ProbePolicy())


def test_a_non_integer_id_is_refused() -> None:
    with pytest.raises(ProbeRejected, match="integer corpus id"):
        validate_probe_request({"id": "42"}, ProbePolicy())


def test_a_boolean_is_not_an_integer_id() -> None:
    with pytest.raises(ProbeRejected, match="integer corpus id"):
        validate_probe_request({"id": True}, ProbePolicy())


def test_k_outside_the_permitted_range_is_refused() -> None:
    for bad_k in (0, -1, MAX_K + 1):
        with pytest.raises(ProbeRejected, match="'k' must be between"):
            validate_probe_request({"id": 1, "k": bad_k}, ProbePolicy())


def test_a_non_integer_k_is_refused() -> None:
    with pytest.raises(ProbeRejected, match="'k' must be an integer"):
        validate_probe_request({"id": 1, "k": 2.5}, ProbePolicy())


# --- rate limiting -----------------------------------------------------------


def test_requests_within_the_window_are_admitted() -> None:
    limiter = RateLimiter(policy=ProbePolicy(max_requests=3), clock=_Clock())

    for _ in range(3):
        limiter.check("127.0.0.1")

    assert limiter.remaining("127.0.0.1") == 0


def test_exceeding_the_window_is_refused_with_a_retry_hint() -> None:
    clock = _Clock()
    limiter = RateLimiter(
        policy=ProbePolicy(max_requests=2, window_seconds=60.0), clock=clock
    )
    limiter.check("client")
    clock.tick(10.0)
    limiter.check("client")

    with pytest.raises(ProbeRejected) as excinfo:
        limiter.check("client")

    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after_seconds == pytest.approx(50.0)


def test_the_window_slides() -> None:
    clock = _Clock()
    limiter = RateLimiter(
        policy=ProbePolicy(max_requests=1, window_seconds=10.0), clock=clock
    )
    limiter.check("client")

    clock.tick(10.1)
    limiter.check("client")

    assert limiter.remaining("client") == 0


def test_clients_are_limited_independently() -> None:
    limiter = RateLimiter(policy=ProbePolicy(max_requests=1), clock=_Clock())
    limiter.check("a")

    limiter.check("b")

    assert limiter.remaining("a") == 0
    assert limiter.remaining("b") == 0


def test_an_unseen_client_has_its_full_allowance() -> None:
    limiter = RateLimiter(policy=ProbePolicy(max_requests=7), clock=_Clock())

    assert limiter.remaining("fresh") == 7


# --- caching -----------------------------------------------------------------


def test_results_are_cached_per_point_and_k() -> None:
    cache = ProbeCache(max_size=4)
    cache.put((1, 10), "result")

    assert cache.get((1, 10)) == "result"
    assert cache.get((1, 5)) is None
    assert cache.hits == 1
    assert cache.misses == 1


def test_the_cache_evicts_least_recently_used_entries() -> None:
    cache = ProbeCache(max_size=2)
    cache.put((1, 10), "a")
    cache.put((2, 10), "b")
    cache.get((1, 10))

    cache.put((3, 10), "c")

    assert cache.get((2, 10)) is None
    assert cache.get((1, 10)) == "a"
    assert len(cache) == 2


def test_reinserting_a_key_refreshes_it_without_growing_the_cache() -> None:
    cache = ProbeCache(max_size=2)
    cache.put((1, 10), "a")
    cache.put((1, 10), "b")

    assert len(cache) == 1
    assert cache.get((1, 10)) == "b"


def test_invalidating_a_point_drops_every_k_for_it() -> None:
    """A point deleted mid-session must not keep serving a stale probe."""
    cache = ProbeCache(max_size=8)
    cache.put((1, 5), "a")
    cache.put((1, 10), "b")
    cache.put((2, 5), "c")

    removed = cache.invalidate(1)

    assert removed == 2
    assert cache.get((1, 5)) is None
    assert cache.get((2, 5)) == "c"


def test_a_zero_sized_cache_stores_nothing() -> None:
    cache = ProbeCache(max_size=0)

    cache.put((1, 1), "x")

    assert len(cache) == 0
    assert cache.get((1, 1)) is None
