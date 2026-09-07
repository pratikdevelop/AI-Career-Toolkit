"""Exact-match response cache.

A prompt built from the exact same resume + job description text (e.g. a
double-submit, or two testers trying the built-in example) doesn't need
to pay for another model call. This is deliberately *exact*-match, keyed
by a hash of the prompt, not semantic similarity: semantic caching needs
an embeddings call and a vector index, which isn't worth the added cost
and infrastructure at "a few testers" scale. The ``ResponseCache``
protocol keeps that swap possible later without touching callers.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Protocol


class ResponseCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...
    def set(self, key: str, value: dict[str, Any]) -> None: ...


def make_cache_key(*parts: str) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


class InMemoryTTLCache:
    """Thread-safe LRU cache with a TTL, good enough for a single Streamlit
    process. Swap in a Redis-backed implementation of the same protocol if
    this ever runs as multiple replicas."""

    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._data: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)
