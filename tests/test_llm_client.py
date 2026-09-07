"""Unit tests for the resilience primitives that don't require the Gemini
SDK to be importable. The concrete ``GeminiLLMClient`` itself is exercised
via a mocked ``google.generativeai`` module or a live-key integration
test, since its behaviour is mostly a thin, well-typed wrapper around
that SDK plus these primitives.
"""
from __future__ import annotations

import time

import pytest

from careerreshape.core.llm.cache import InMemoryTTLCache, make_cache_key
from careerreshape.core.llm.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_cache_key_is_stable_and_order_sensitive() -> None:
    assert make_cache_key("a", "b") == make_cache_key("a", "b")
    assert make_cache_key("a", "b") != make_cache_key("b", "a")


def test_cache_returns_none_after_ttl_expires() -> None:
    cache = InMemoryTTLCache(ttl_seconds=0.01, max_entries=10)
    cache.set("k", {"v": 1})
    assert cache.get("k") == {"v": 1}
    time.sleep(0.02)
    assert cache.get("k") is None


def test_cache_evicts_least_recently_used_when_full() -> None:
    cache = InMemoryTTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})
    cache.set("c", {"v": 3})  # should evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == {"v": 2}
    assert cache.get("c") == {"v": 3}


def test_circuit_breaker_opens_after_threshold_and_blocks_calls() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    for _ in range(3):
        breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_circuit_breaker_half_opens_after_reset_window() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=0.01)
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    time.sleep(0.02)
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.before_call()  # should not raise -- half-open allows a trial call


def test_circuit_breaker_recovers_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_seconds=0.01)
    breaker.record_failure()
    time.sleep(0.02)
    breaker.before_call()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
