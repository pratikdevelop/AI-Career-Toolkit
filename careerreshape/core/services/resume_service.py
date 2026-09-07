"""Business logic for the resume optimizer -- no Streamlit imports here.

Everything this module needs (an ``LLMClient``, a ``Settings`` object, a
logger) is passed in via the constructor, which is what makes it testable
with a fake LLM client and no UI framework at all.
"""
from __future__ import annotations

import time

from careerreshape.config import Settings
from careerreshape.core.analytics.logger import StructuredLogger
from careerreshape.core.exceptions import LLMResponseFormatError
from careerreshape.core.llm.cache import make_cache_key
from careerreshape.core.llm.client import LLMClient
from careerreshape.core.models import ResumeOptimizationResult
from careerreshape.core.security.sanitizer import (
    make_delimiter,
    sanitize_user_content,
    validate_length,
    wrap_as_data,
)

_PROMPT_TEMPLATE = """You are an expert resume writer and ATS (Applicant Tracking System) specialist.

Given the RESUME and JOB DESCRIPTION data blocks below, do the following and respond ONLY in \
valid JSON (no markdown fences, no preamble):

{{
  "match_score": <integer 0-100, how well the resume matches the job description>,
  "missing_keywords": [<important keywords/skills from the job description missing in the resume>],
  "strengths": [<3-5 things the resume already does well for this job>],
  "improvement_suggestions": [<3-6 specific, actionable suggestions>],
  "optimized_resume": "<a rewritten, improved version of the resume text, tailored to this job, \
keeping it truthful to the original content -- do not invent experience>",
  "cover_letter": "<a concise, tailored 3-paragraph cover letter based on the resume and job description>"
}}

{resume_block}

{job_block}
"""


class ResumeOptimizerService:
    def __init__(self, *, llm_client: LLMClient, settings: Settings, logger: StructuredLogger) -> None:
        self._llm_client = llm_client
        self._settings = settings
        self._logger = logger

    async def optimize(self, resume_text: str, job_description: str) -> ResumeOptimizationResult:
        started_at = time.monotonic()

        resume_text = validate_length(
            resume_text, max_chars=self._settings.max_input_chars, field_name="resume"
        )
        job_description = validate_length(
            job_description, max_chars=self._settings.max_input_chars, field_name="job description"
        )
        resume_flag = sanitize_user_content(resume_text, field_name="resume").flagged
        job_flag = sanitize_user_content(job_description, field_name="job_description").flagged

        delimiter = make_delimiter()
        prompt = _PROMPT_TEMPLATE.format(
            resume_block=wrap_as_data("RESUME", resume_text, delimiter),
            job_block=wrap_as_data("JOB DESCRIPTION", job_description, delimiter),
        )
        cache_key = make_cache_key("resume_v1", resume_text, job_description)

        self._logger.info(
            "resume_optimization.started",
            resume_chars=len(resume_text),
            job_chars=len(job_description),
            flagged_input=resume_flag or job_flag,
        )

        try:
            raw = await self._llm_client.generate_json_async(prompt, cache_key=cache_key)
            result = ResumeOptimizationResult.from_llm_dict(raw)
        except ValueError as exc:
            raise LLMResponseFormatError(f"Model response failed schema validation: {exc}") from exc
        except Exception:
            self._logger.error(
                "resume_optimization.failed",
                duration_ms=int((time.monotonic() - started_at) * 1000),
            )
            raise

        self._logger.info(
            "resume_optimization.completed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
            match_score=result.match_score,
        )
        return result
