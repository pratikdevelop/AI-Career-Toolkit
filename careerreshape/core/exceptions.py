"""Typed exception hierarchy.

Every layer raises one of these instead of leaking SDK/library-specific
exceptions upward. The UI layer only ever needs to catch
``CareerReshapeError`` and its handful of subclasses to show an honest,
specific message -- it never has to know the LLM provider is Gemini or
that fetching uses httpx.
"""
from __future__ import annotations


class CareerReshapeError(Exception):
    """Base class for all application errors."""


# ---- LLM errors -------------------------------------------------------

class LLMError(CareerReshapeError):
    """Base class for LLM-related failures."""


class LLMRateLimitError(LLMError):
    """The provider returned a 429 / resource-exhausted response."""


class LLMTimeoutError(LLMError):
    """The call exceeded the configured timeout."""


class LLMAuthError(LLMError):
    """The API key was rejected. Not retryable."""


class LLMResponseFormatError(LLMError):
    """The model's response could not be parsed into the expected schema,
    even after a repair attempt."""


class LLMUnavailableError(LLMError):
    """All models/providers failed, or the circuit breaker is open."""


# ---- Input / document errors -------------------------------------------

class InputValidationError(CareerReshapeError):
    """User-supplied input failed validation before it reached the LLM."""


class DocumentParsingError(CareerReshapeError):
    """Base class for file-parsing failures."""


class UnsupportedFileTypeError(DocumentParsingError):
    pass


class FileTooLargeError(DocumentParsingError):
    pass


class MalformedDocumentError(DocumentParsingError):
    pass


# ---- URL fetching errors ------------------------------------------------

class UrlFetchError(CareerReshapeError):
    """Base class for URL-fetching failures."""


class UnsafeUrlError(UrlFetchError):
    """The URL was rejected by SSRF/allowlist validation before any
    network request was made."""


class FetchBlockedError(UrlFetchError):
    """The remote site actively blocked or gated the request (e.g. a
    LinkedIn login wall)."""
