"""Streamlit rendering for the Resume Optimizer tab.

This module only renders UI and translates typed exceptions into
messages -- all of the actual work (parsing, fetching, calling the LLM)
happens in service/utility modules that don't import Streamlit at all.
"""
from __future__ import annotations

import asyncio

import streamlit as st

from careerreshape.config import Settings
from careerreshape.core.analytics.logger import StructuredLogger
from careerreshape.core.exceptions import CareerReshapeError
from careerreshape.core.paywall.usage_tracker import UsageTracker
from careerreshape.core.services import document_parser, web_fetcher
from careerreshape.core.services.docx_builder import build_resume_docx
from careerreshape.core.services.resume_service import ResumeOptimizerService
from careerreshape.ui.error_messages import friendly_error_message

EXAMPLE_RESUME = """Jordan Lee
Marketing Coordinator with 3 years of experience in social media management and email campaigns.

Experience:
- Managed social media accounts for a 50-person retail company, growing followers by 40%
- Wrote and scheduled weekly email newsletters using Mailchimp
- Coordinated with design team on marketing assets
- Tracked campaign performance in spreadsheets

Skills: Social media, Mailchimp, Canva, basic Excel, team communication
Education: B.A. Communications, State University, 2021
"""

EXAMPLE_JOB = """Senior Digital Marketing Specialist

We're looking for a Senior Digital Marketing Specialist to lead our growth marketing efforts.

Responsibilities:
- Own paid and organic social media strategy across platforms
- Analyze campaign performance using Google Analytics and HubSpot
- Manage a $50k/month digital ad budget across Meta and Google Ads
- Lead A/B testing for email and landing page conversion
- Mentor junior marketing team members

Requirements:
- 5+ years digital marketing experience
- Proficiency in Google Analytics, HubSpot, and Meta Ads Manager
- Proven track record managing paid ad budgets
- Strong data analysis and reporting skills
"""


def render_resume_tab(
    *,
    settings: Settings,
    api_key: str | None,
    service: ResumeOptimizerService,
    usage_tracker: UsageTracker,
    logger: StructuredLogger,
) -> None:
    if "example_loaded" not in st.session_state:
        st.session_state.example_loaded = False

    example_col, _ = st.columns([1, 3])
    with example_col:
        if st.button("\u2728 Try an example", use_container_width=True):
            st.session_state.example_loaded = True

    if st.session_state.example_loaded:
        st.info(
            "Example resume and job description loaded below \u2014 click "
            "**Analyze & Optimize** to see it in action."
        )

    col1, col2 = st.columns(2)
    resume_text = ""
    job_desc = ""

    with col1:
        st.subheader("\U0001F4E4 Your Resume")
        if st.session_state.example_loaded:
            resume_text = EXAMPLE_RESUME
            st.success("\u2705 Using example resume")
            with st.expander("Preview example resume"):
                st.text(resume_text)
        else:
            resume_file = st.file_uploader(
                "Upload your resume",
                type=["pdf", "docx", "txt"],
                help="PDF, Word (.docx), or plain text (.txt)",
            )
            if resume_file is not None:
                try:
                    parsed = document_parser.parse_document(
                        resume_file.getvalue(), resume_file.name, settings
                    )
                    resume_text = parsed.text
                    if not resume_text:
                        st.warning("Couldn't extract text from that file \u2014 it may be a scanned image PDF.")
                    else:
                        st.success(f"\u2705 Loaded {resume_file.name} ({parsed.char_count} characters)")
                        if parsed.truncated:
                            st.warning("Resume was long \u2014 trimmed to fit the input limit.")
                        with st.expander("Preview extracted text"):
                            st.text(resume_text[:2000] + ("..." if len(resume_text) > 2000 else ""))
                except CareerReshapeError as exc:
                    st.error(friendly_error_message(exc))

    with col2:
        st.subheader("\U0001F517 Job Description")
        if st.session_state.example_loaded:
            job_desc = EXAMPLE_JOB
            st.success("\u2705 Using example job posting")
            with st.expander("Preview example job posting"):
                st.text(job_desc)
        else:
            job_input_mode = st.radio(
                "How do you want to provide the job posting?", ["From URL", "Paste text"], horizontal=True
            )
            if job_input_mode == "From URL":
                job_url = st.text_input("Job posting URL", placeholder="https://company.com/careers/job-posting")
                if job_url:
                    with st.spinner("Fetching job description..."):
                        try:
                            fetched = asyncio.run(web_fetcher.fetch_job_description(job_url, settings))
                            job_desc = fetched.text
                            if not job_desc:
                                st.warning("Couldn't extract readable text from that page.")
                            else:
                                st.success(f"\u2705 Fetched job posting ({len(job_desc)} characters)")
                                with st.expander("Preview fetched text"):
                                    st.text(job_desc[:2000] + ("..." if len(job_desc) > 2000 else ""))
                        except CareerReshapeError as exc:
                            st.error(friendly_error_message(exc) + " Try 'Paste text' instead.")
            else:
                job_desc = st.text_area(
                    "Paste the job posting text here", height=250, placeholder="Paste the job description..."
                )

    analyze_btn = st.button("\U0001F680 Analyze & Optimize", type="primary", use_container_width=True)

    if analyze_btn:
        if not api_key:
            st.error("\u26a0\ufe0f Please enter your free Gemini API key in the sidebar.")
        elif not resume_text.strip():
            st.error("\u26a0\ufe0f Please upload a resume file.")
        elif not job_desc.strip():
            st.error("\u26a0\ufe0f Please provide a job description (via URL or paste).")
        else:
            decision = usage_tracker.check_and_consume(st.session_state)
            if not decision.allowed:
                st.warning(f"You've used your {settings.free_uses_per_session} free optimizations for this session.")
                st.link_button("\U0001F4B3 Unlock unlimited optimizations", decision.stripe_link, use_container_width=True)
                st.stop()

            with st.spinner("Analyzing your resume against the job description..."):
                try:
                    result = asyncio.run(service.optimize(resume_text, job_desc))
                except CareerReshapeError as exc:
                    st.error(friendly_error_message(exc))
                    return

            st.subheader("\U0001F4CA Match Score")
            st.progress(result.match_score / 100)
            st.metric("ATS Match Score", f"{result.match_score}/100")

            tab1, tab2, tab3, tab4 = st.tabs(
                ["\U0001F511 Keywords & Strengths", "\U0001F4A1 Suggestions", "\U0001F4DD Optimized Resume", "\u2709\ufe0f Cover Letter"]
            )

            with tab1:
                st.markdown("**Missing Keywords**")
                if result.missing_keywords:
                    st.write(", ".join(f"`{kw}`" for kw in result.missing_keywords))
                else:
                    st.success("No major keywords missing!")
                st.markdown("**Strengths**")
                for s in result.strengths:
                    st.markdown(f"- \u2705 {s}")

            with tab2:
                st.markdown("**Improvement Suggestions**")
                for i, s in enumerate(result.improvement_suggestions, 1):
                    st.markdown(f"{i}. {s}")

            with tab3:
                st.markdown("**Optimized Resume**")
                st.text_area("Copy your optimized resume:", value=result.optimized_resume, height=400)
                docx_buffer = build_resume_docx(result.optimized_resume)
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    st.download_button(
                        "\u2b07\ufe0f Download as Word (.docx)",
                        docx_buffer,
                        file_name="optimized_resume.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                with dl_col2:
                    st.download_button(
                        "\u2b07\ufe0f Download as Text (.txt)",
                        result.optimized_resume,
                        file_name="optimized_resume.txt",
                        use_container_width=True,
                    )

            with tab4:
                st.markdown("**Tailored Cover Letter**")
                st.text_area("Copy your cover letter:", value=result.cover_letter, height=300)
                st.download_button(
                    "\u2b07\ufe0f Download Cover Letter (.txt)", result.cover_letter, file_name="cover_letter.txt"
                )

    st.markdown("---")
    st.caption(
        "\U0001F4A1 Tip: For best results, use a job URL with the full posting "
        "(skills, responsibilities, requirements) visible on the page."
    )
