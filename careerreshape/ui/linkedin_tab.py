"""Streamlit rendering for the LinkedIn Profile Optimizer tab."""
from __future__ import annotations

import asyncio

import streamlit as st

from careerreshape.config import Settings
from careerreshape.core.analytics.logger import StructuredLogger
from careerreshape.core.exceptions import CareerReshapeError
from careerreshape.core.paywall.usage_tracker import UsageTracker
from careerreshape.core.services import document_parser, web_fetcher
from careerreshape.core.services.linkedin_service import LinkedInOptimizerService
from careerreshape.ui.error_messages import friendly_error_message


def render_linkedin_tab(
    *,
    settings: Settings,
    api_key: str | None,
    service: LinkedInOptimizerService,
    usage_tracker: UsageTracker,
    logger: StructuredLogger,
) -> None:
    st.markdown(
        "Paste your current LinkedIn profile text, or reuse a resume you already have. "
        "Get an optimized headline, About section, experience bullets, and skills to add."
    )

    li_col1, li_col2 = st.columns([2, 1])
    source_text = ""

    with li_col1:
        li_input_mode = st.radio(
            "Source content",
            [
                "Upload LinkedIn PDF export (recommended)",
                "Paste current LinkedIn profile",
                "From LinkedIn URL",
                "Upload a resume instead",
            ],
            horizontal=True,
        )

        if li_input_mode == "Upload LinkedIn PDF export (recommended)":
            with st.expander("\U0001F4CB How to export your LinkedIn profile as a PDF"):
                st.markdown(
                    """
                    1. Go to your LinkedIn profile page
                    2. Click **"More"** (below your profile photo/banner)
                    3. Select **"Save to PDF"**
                    4. Upload the downloaded file below

                    This is the most reliable option \u2014 it's your actual profile content,
                    directly from LinkedIn, with no scraping or blocking involved.
                    """
                )
            li_pdf_file = st.file_uploader(
                "Upload your LinkedIn PDF export", type=["pdf"], key="linkedin_pdf_uploader"
            )
            if li_pdf_file is not None:
                try:
                    parsed = document_parser.parse_document(li_pdf_file.getvalue(), li_pdf_file.name, settings)
                    source_text = parsed.text
                    if not source_text:
                        st.warning("Couldn't extract text from that PDF.")
                    else:
                        st.success(f"\u2705 Loaded {li_pdf_file.name} ({parsed.char_count} characters)")
                        if parsed.truncated:
                            st.warning("Profile export was long \u2014 trimmed to fit the input limit.")
                        with st.expander("Preview extracted text"):
                            st.text(source_text[:2000] + ("..." if len(source_text) > 2000 else ""))
                except CareerReshapeError as exc:
                    st.error(friendly_error_message(exc))

        elif li_input_mode == "Paste current LinkedIn profile":
            source_text = st.text_area(
                "Paste your current headline, About section, and/or experience bullets",
                height=280,
                placeholder="Paste whatever you currently have on your LinkedIn profile...",
            )

        elif li_input_mode == "From LinkedIn URL":
            st.caption(
                "\u26a0\ufe0f LinkedIn blocks nearly all automated fetches, even for public profiles \u2014 "
                "'Upload LinkedIn PDF export' above is far more reliable. This will still try."
            )
            li_url = st.text_input("LinkedIn profile URL", placeholder="https://www.linkedin.com/in/your-profile")
            if li_url:
                with st.spinner("Attempting to fetch profile..."):
                    try:
                        fetched = asyncio.run(web_fetcher.fetch_linkedin_profile(li_url, settings))
                        if fetched.blocked or not fetched.text:
                            st.error(
                                "LinkedIn blocked this fetch (this is expected \u2014 it blocks "
                                "almost all non-logged-in requests). Please use the "
                                "'Upload LinkedIn PDF export' option instead."
                            )
                        else:
                            source_text = fetched.text
                            st.success(
                                f"\u2705 Fetched profile content ({len(source_text)} characters) "
                                "\u2014 please verify it looks correct below."
                            )
                            with st.expander("Preview fetched text"):
                                st.text(source_text[:2000] + ("..." if len(source_text) > 2000 else ""))
                    except CareerReshapeError as exc:
                        st.error(friendly_error_message(exc) + " Please use 'Upload LinkedIn PDF export' instead.")

        else:
            li_resume_file = st.file_uploader(
                "Upload your resume", type=["pdf", "docx", "txt"], key="linkedin_resume_uploader"
            )
            if li_resume_file is not None:
                try:
                    parsed = document_parser.parse_document(li_resume_file.getvalue(), li_resume_file.name, settings)
                    source_text = parsed.text
                    if not source_text:
                        st.warning("Couldn't extract text from that file \u2014 it may be a scanned image PDF.")
                    else:
                        st.success(f"\u2705 Loaded {li_resume_file.name} ({parsed.char_count} characters)")
                        if parsed.truncated:
                            st.warning("Resume was long \u2014 trimmed to fit the input limit.")
                except CareerReshapeError as exc:
                    st.error(friendly_error_message(exc))

    with li_col2:
        target_role = st.text_input("Target role/industry (optional)", placeholder="e.g. Senior Product Manager, fintech")
        st.caption("Leave blank to optimize generally rather than for a specific role.")

    li_analyze_btn = st.button("\U0001F680 Optimize My LinkedIn Profile", type="primary", use_container_width=True)

    if li_analyze_btn:
        if not api_key:
            st.error("\u26a0\ufe0f Please enter your free Gemini API key in the sidebar.")
        elif not source_text.strip():
            st.error("\u26a0\ufe0f Please paste your profile text or upload a resume.")
        else:
            decision = usage_tracker.check_and_consume(st.session_state)
            if not decision.allowed:
                st.warning(f"You've used your {settings.free_uses_per_session} free optimizations for this session.")
                st.link_button("\U0001F4B3 Unlock unlimited optimizations", decision.stripe_link, use_container_width=True)
                st.stop()

            with st.spinner("Optimizing your LinkedIn profile..."):
                try:
                    result = asyncio.run(service.optimize(source_text, target_role))
                except CareerReshapeError as exc:
                    st.error(friendly_error_message(exc))
                    return

            li_tab1, li_tab2, li_tab3, li_tab4 = st.tabs(
                ["\u2728 Headline", "\U0001F4DD About Section", "\U0001F4BC Experience Bullets", "\U0001F3F7\ufe0f Skills & Notes"]
            )

            with li_tab1:
                st.text_area("Copy your new headline:", value=result.headline, height=80)

            with li_tab2:
                st.text_area("Copy your new About section:", value=result.about_section, height=300)

            with li_tab3:
                st.markdown("**Rewritten Experience Bullets**")
                for b in result.experience_bullets:
                    st.markdown(f"- {b}")

            with li_tab4:
                st.markdown("**Skills to Add**")
                if result.skills_to_add:
                    st.write(", ".join(f"`{s}`" for s in result.skills_to_add))
                st.markdown("**Why These Changes Help**")
                for n in result.improvement_notes:
                    st.markdown(f"- {n}")

    st.markdown("---")
    st.caption("\U0001F4A1 Tip: LinkedIn headlines perform best under 220 characters and front-load your role + key skill.")
