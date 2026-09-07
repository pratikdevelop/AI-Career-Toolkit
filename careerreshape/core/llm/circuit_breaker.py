"""A minimal circuit breaker for the LLM client.

If the provider is genuinely down, retrying every single user's request
with full backoff still hammers a dead endpoint and makes every user wait
through the full retry budget before failing. Once ``failure_threshold``
consecutive failures happen, the breaker opens and fails fast for
``reset_seconds`` before allowing a single trial call through
(half-open) to test recovery.
"""
from __future__ import annotations

import time
from enum import Enum
from threading import Lock


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised by ``CircuitBreaker.before_call`` when the circuit is open."""


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int, reset_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open_locked()
            return self._state

    def _maybe_half_open_locked(self) -> None:
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self._reset_seconds:
                self._state = CircuitState.HALF_OPEN

    def before_call(self) -> None:
        with self._lock:
            self._maybe_half_open_locked()
            if self._state is CircuitState.OPEN:
                remaining = self._reset_seconds - (time.monotonic() - (self._opened_at or 0.0))
                raise CircuitOpenError(f"Circuit open; retry after {max(0.0, remaining):.0f}s")

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._state is CircuitState.HALF_OPEN or self._consecutive_failures >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
