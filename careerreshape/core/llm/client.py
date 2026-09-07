"""The seam between business logic and any specific LLM provider.

``ResumeOptimizerService`` / ``LinkedInOptimizerService`` depend only on
this ``Protocol``, never on the Gemini SDK directly. That's what makes
them unit-testable with an in-memory fake, and what makes swapping or
adding a fallback provider a matter of writing one new adapter class
instead of touching business logic.
"""
from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """A provider-agnostic client that turns a prompt into a parsed JSON dict."""

    def generate_json(self, prompt: str, *, cache_key: str | None = None) -> dict[str, Any]:
        """Synchronous call. Raises subclasses of ``LLMError`` on failure."""
        ...

    async def generate_json_async(
        self, prompt: str, *, cache_key: str | None = None
    ) -> dict[str, Any]:
        """Async call, so independent LLM/network calls can run concurrently."""
        ...
