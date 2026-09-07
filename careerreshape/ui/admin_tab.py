"""Hidden admin analytics view, gated by a query-string admin key.

Kept from the original design (still fine for "a few testers" scale) but
isolated so it's obvious this needs a real auth mechanism (e.g. a login
behind Streamlit's built-in auth, or moving this to a separate internal
tool) before this app carries any real, sensitive usage data. The admin
key is still visible in the URL/referrer/logs -- flagged in
README_ARCHITECTURE.md as a follow-up, not solved here, since a proper
fix (real auth) is a bigger change than this pass's scope.
"""
from __future__ import annotations

import streamlit as st

from careerreshape.config import Settings
from careerreshape.core.analytics.logger import StructuredLogger


def render_admin_tab_if_authorized(settings: Settings, logger: StructuredLogger) -> None:
    if not settings.admin_key:
        return
    if st.query_params.get("admin") != settings.admin_key:
        return

    st.markdown("---")
    st.header("\U0001F4CA Admin: Usage Analytics")

    stats = logger.usage_summary()
    if stats is None:
        st.info("No analytics data yet, or ANALYTICS_WEBHOOK_URL isn't configured.")
    else:
        col_a, col_b = st.columns(2)
        col_a.metric("Total events (all time)", stats.get("total_events", 0))
        col_b.metric("Events today", stats.get("events_today", 0))

        st.markdown("**Breakdown by event type**")
        counts = stats.get("counts_by_type", {})
        if counts:
            for event_type, count in sorted(counts.items(), key=lambda item: -item[1]):
                st.markdown(f"- `{event_type}`: {count}")
        else:
            st.caption("No events logged yet.")

    if st.button("\U0001F504 Refresh stats"):
        st.rerun()
