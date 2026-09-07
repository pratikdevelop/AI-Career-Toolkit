"""Application configuration.

Loads all runtime configuration from a mapping (typically ``st.secrets``)
into a single typed, immutable ``Settings`` object. Nothing else in the
codebase should read secrets directly -- this is the one seam that knows
about the secrets source, which is what makes every other module testable
without Streamlit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    gemini_api_key: Optional[str]
    stripe_payment_link: Optional[str]
    admin_key: Optional[str]
    analytics_webhook_url: Optional[str]

    max_input_chars: int = 15_000
    max_fetch_chars: int = 8_000
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 MB
    max_decompressed_docx_bytes: int = 40 * 1024 * 1024  # zip-bomb guard

    request_timeout_seconds: float = 12.0
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 4
    llm_backoff_base_seconds: float = 1.0
    llm_backoff_max_seconds: float = 20.0

    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: float = 60.0

    model_list_cache_ttl_seconds: float = 3600.0
    response_cache_ttl_seconds: float = 3600.0
    response_cache_max_entries: int = 256

    free_uses_per_session: int = 3

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def paywall_enabled(self) -> bool:
        return bool(self.stripe_payment_link)


def load_settings(
    secrets: Mapping[str, object], *, runtime_api_key: Optional[str] = None
) -> Settings:
    """Build ``Settings`` from a secrets-like mapping.

    ``runtime_api_key`` lets a visitor's own pasted key (used when no
    shared key is configured) override the configured one, matching the
    original app's behaviour, without this module ever importing
    Streamlit.
    """

    def _get(key: str) -> Optional[str]:
        value = secrets.get(key)
        return str(value) if value else None

    return Settings(
        gemini_api_key=runtime_api_key or _get("GEMINI_API_KEY"),
        stripe_payment_link=_get("STRIPE_PAYMENT_LINK"),
        admin_key=_get("ADMIN_KEY"),
        analytics_webhook_url=_get("ANALYTICS_WEBHOOK_URL"),
    )
