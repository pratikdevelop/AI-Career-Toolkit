"""Test doubles."""
from __future__ import annotations

from typing import Any


class FakeLLMClient:
    """Implements the ``LLMClient`` protocol for tests.

    Configure with either a canned response dict or an exception to
    raise, without touching any real network or SDK. ``calls`` records
    every prompt passed in, so tests can assert on prompt construction
    (e.g. that user content was wrapped in delimiters).
    """

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.response = response
        self.exception = exception
        self.calls: list[str] = []

    def generate_json(self, prompt: str, *, cache_key: str | None = None) -> dict[str, Any]:
        self.calls.append(prompt)
        if self.exception is not None:
            raise self.exception
        assert self.response is not None
        return self.response

    async def generate_json_async(
        self, prompt: str, *, cache_key: str | None = None
    ) -> dict[str, Any]:
        return self.generate_json(prompt, cache_key=cache_key)
