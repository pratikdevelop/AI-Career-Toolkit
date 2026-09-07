"""Sidebar: API key entry / status."""
from __future__ import annotations

import streamlit as st

from careerreshape.config import Settings


def render_sidebar(settings: Settings) -> str | None:
    st.sidebar.title("\u2699\ufe0f Setup")

    api_key = settings.gemini_api_key
    if api_key:
        st.sidebar.success("\u2705 Using built-in API key \u2014 just upload and go!")
    else:
        st.sidebar.markdown(
            """
            This app uses **Google Gemini's free API**.

            1. Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
            2. Paste it below (it's never stored)
            """
        )
        api_key = st.sidebar.text_input("Gemini API Key", type="password") or None

    st.sidebar.markdown("---")
    st.sidebar.caption("CareerReshape \u00b7 No data is saved after your session ends.")
    return api_key
