"""Maps typed exceptions to user-facing messages.

Centralised so both tabs show consistent, non-leaky error text -- neither
tab needs to know about ``LLMRateLimitError`` vs ``LLMUnavailableError``
internals, just that this function always returns something safe to show
a user (never a raw SDK exception string, unlike the original
``st.error(f"Something went wrong: {e}")``).
"""
from __future__ import annotations

from careerreshape.core.exceptions import (
    CareerReshapeError,
    DocumentParsingError,
    LLMError,
    LLMRateLimitError,
    LLMUnavailableError,
    UrlFetchError,
)


def friendly_error_message(exc: Exception) -> str:
    if isinstance(exc, LLMRateLimitError):
        return "The AI provider is rate-limiting requests right now. Please try again in a minute."
    if isinstance(exc, LLMUnavailableError):
        return "The AI provider is temporarily unavailable. Please try again shortly."
    if isinstance(exc, LLMError):
        return "The AI response couldn't be processed. Please try again."
    if isinstance(exc, DocumentParsingError):
        return f"Couldn't read that file: {exc}"
    if isinstance(exc, UrlFetchError):
        return f"Couldn't fetch that URL: {exc}"
    if isinstance(exc, CareerReshapeError):
        return str(exc)
    return "Something unexpected went wrong. Please try again."
