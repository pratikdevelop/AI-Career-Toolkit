"""Business logic for the LinkedIn profile optimizer."""
from __future__ import annotations

import time

from careerreshape.config import Settings
from careerreshape.core.analytics.logger import StructuredLogger
from careerreshape.core.exceptions import LLMResponseFormatError
from careerreshape.core.llm.cache import make_cache_key
from careerreshape.core.llm.client import LLMClient
from careerreshape.core.models import LinkedInOptimizationResult
from careerreshape.core.security.sanitizer import (
    make_delimiter,
    sanitize_user_content,
    validate_length,
    wrap_as_data,
)

_PROMPT_TEMPLATE = """You are an expert LinkedIn profile writer and personal branding strategist.

Given the SOURCE CONTENT data block below (a resume or existing LinkedIn profile text), produce \
an optimized LinkedIn profile. Respond ONLY in valid JSON (no markdown fences, no preamble):

{{
  "headline": "<a compelling LinkedIn headline, under 220 characters, keyword-rich>",
  "about_section": "<a 3-4 paragraph LinkedIn About section, written in first person, engaging \
and specific -- not generic corporate language>",
  "experience_bullets": [<5-8 rewritten, achievement-focused experience bullet points, each \
starting with a strong action verb>],
  "skills_to_add": [<8-12 relevant skills to add to the LinkedIn Skills section>],
  "improvement_notes": [<3-5 specific tips on what was weak in the original and why the changes help>]
}}

{role_line}

{source_block}
"""


class LinkedInOptimizerService:
    def __init__(self, *, llm_client: LLMClient, settings: Settings, logger: StructuredLogger) -> None:
        self._llm_client = llm_client
        self._settings = settings
        self._logger = logger

    async def optimize(self, source_text: str, target_role: str = "") -> LinkedInOptimizationResult:
        started_at = time.monotonic()

        source_text = validate_length(
            source_text, max_chars=self._settings.max_input_chars, field_name="profile source"
        )
        flagged = sanitize_user_content(source_text, field_name="linkedin_source").flagged

        role_line = (
            f"Target role/industry to tailor toward: {target_role}"
            if target_role.strip()
            else "No specific target role given -- optimize for general career growth in the same field."
        )
        delimiter = make_delimiter()
        prompt = _PROMPT_TEMPLATE.format(
            role_line=role_line,
            source_block=wrap_as_data("SOURCE CONTENT", source_text, delimiter),
        )
        cache_key = make_cache_key("linkedin_v1", source_text, target_role)

        self._logger.info(
            "linkedin_optimization.started",
            source_chars=len(source_text),
            flagged_input=flagged,
        )

        try:
            raw = await self._llm_client.generate_json_async(prompt, cache_key=cache_key)
            result = LinkedInOptimizationResult.from_llm_dict(raw)
        except ValueError as exc:
            raise LLMResponseFormatError(f"Model response failed schema validation: {exc}") from exc
        except Exception:
            self._logger.error(
                "linkedin_optimization.failed",
                duration_ms=int((time.monotonic() - started_at) * 1000),
            )
            raise

        self._logger.info(
            "linkedin_optimization.completed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )
        return result
