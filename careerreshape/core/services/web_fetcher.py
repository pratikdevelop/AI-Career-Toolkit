"""Async, SSRF-safe fetching of job postings and LinkedIn profile pages.

Uses ``httpx`` (async-native) instead of ``requests`` so this can run
concurrently with other I/O via ``asyncio.gather`` at the service/UI
layer, instead of blocking serially for every fetch.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from careerreshape.config import Settings
from careerreshape.core.exceptions import UrlFetchError
from careerreshape.core.models import FetchedContent
from careerreshape.core.security.url_validator import assert_safe_url

_JOB_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CareerReshapeBot/1.0)"}
_LINKEDIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_LINKEDIN_BLOCK_SIGNALS = ("join linkedin", "sign in to view", "authwall", "join now")


def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
    return "\n".join(lines)


async def fetch_job_description(url: str, settings: Settings) -> FetchedContent:
    assert_safe_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get(url, headers=_JOB_HEADERS)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UrlFetchError(f"Could not fetch {url}: {exc}") from exc

    # Redirects can land on a different host than the one that was
    # validated -- re-validate the final URL before trusting its content.
    assert_safe_url(str(response.url))

    text = _clean_text(response.text)
    truncated = len(text) > settings.max_fetch_chars
    return FetchedContent(
        text=text[: settings.max_fetch_chars],
        source_url=str(response.url),
        truncated=truncated,
    )


async def fetch_linkedin_profile(url: str, settings: Settings) -> FetchedContent:
    assert_safe_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds, follow_redirects=True
        ) as client:
            response = await client.get(url, headers=_LINKEDIN_HEADERS)
    except httpx.HTTPError as exc:
        raise UrlFetchError(f"Could not fetch {url}: {exc}") from exc

    if response.status_code in (403, 999):
        return FetchedContent(
            text="",
            source_url=url,
            truncated=False,
            blocked=True,
            block_reason="LinkedIn returned a blocked/bot-detection status code",
        )

    assert_safe_url(str(response.url))
    text = _clean_text(response.text)
    looks_blocked = len(text) < 1500 or any(
        signal in text.lower() for signal in _LINKEDIN_BLOCK_SIGNALS
    )
    if looks_blocked:
        return FetchedContent(
            text="",
            source_url=str(response.url),
            truncated=False,
            blocked=True,
            block_reason="Response looked like a LinkedIn login/auth wall",
        )

    truncated = len(text) > settings.max_fetch_chars
    return FetchedContent(
        text=text[: settings.max_fetch_chars],
        source_url=str(response.url),
        truncated=truncated,
    )
