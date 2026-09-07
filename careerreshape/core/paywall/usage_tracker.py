"""Soft, session-scoped usage cap with an optional Stripe upsell.

Kept intentionally simple, matching the original design decision: this
does not track users across sessions or devices, and is not meant to.
The only change from the original is that it no longer reaches into
``st.session_state`` directly -- it depends on a plain
``MutableMapping``-like object, so it's testable with a bare ``dict`` and
portable if the session-state backend ever changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping, Optional

_SESSION_KEY = "uses_this_session"


@dataclass(frozen=True)
class PaywallDecision:
    allowed: bool
    stripe_link: Optional[str]


class UsageTracker:
    def __init__(self, *, free_uses_per_session: int, stripe_payment_link: Optional[str]) -> None:
        self._free_uses = free_uses_per_session
        self._stripe_link = stripe_payment_link

    def check_and_consume(self, session_state: MutableMapping[str, int]) -> PaywallDecision:
        if not self._stripe_link:
            return PaywallDecision(allowed=True, stripe_link=None)

        used = session_state.get(_SESSION_KEY, 0)
        if used >= self._free_uses:
            return PaywallDecision(allowed=False, stripe_link=self._stripe_link)

        session_state[_SESSION_KEY] = used + 1
        return PaywallDecision(allowed=True, stripe_link=self._stripe_link)
