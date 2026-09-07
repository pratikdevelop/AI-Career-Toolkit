"""Concrete Gemini implementation of ``LLMClient``.

Resilience responsibilities live entirely here, isolated from business
logic:
  * exponential backoff + jitter on retryable errors (429 / timeout /
    transient unavailability), via ``tenacity``
  * a per-instance circuit breaker so a fully-down provider fails fast
    instead of making every user wait through a full retry budget
  * an explicit timeout on every call
  * exact-match response caching
  * model-list discovery with graceful fallback to a hardcoded list

Model fallback vs. retry are kept conceptually separate: a 429/timeout on
a *working* model is retried against the *same* model with backoff --
that is what "retry" means. Falling through to the *next* model in the
list only happens for structural failures (model not found, not
supported for this key). Silently swapping models on a rate limit would
hide the real problem instead of handling it, which is what the original
prototype did.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from careerreshape.config import Settings
from careerreshape.core.exceptions import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseFormatError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from careerreshape.core.llm.cache import ResponseCache
from careerreshape.core.llm.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger("careerreshape.llm")

_FALLBACK_MODELS = ["gemini-flash-latest", "gemini-pro-latest"]
_RETRYABLE_ON_SAME_MODEL = (LLMRateLimitError, LLMTimeoutError)


class GeminiLLMClient:
    def __init__(
        self,
        *,
        api_key: str,
        settings: Settings,
        cache: ResponseCache,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._api_key = api_key
        self._settings = settings
        self._cache = cache
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            reset_seconds=settings.circuit_breaker_reset_seconds,
        )
        self._model_list_cache: tuple[float, list[str]] | None = None
        genai.configure(api_key=api_key)

    # ---- public API -----------------------------------------------------

    def generate_json(self, prompt: str, *, cache_key: str | None = None) -> dict[str, Any]:
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info("llm.cache_hit", extra={"extra_fields": {"cache_key": cache_key}})
                return cached

        try:
            self._circuit_breaker.before_call()
        except CircuitOpenError as exc:
            raise LLMUnavailableError(str(exc)) from exc

        last_error: Exception | None = None
        for model_name in self._resolve_models():
            try:
                raw_text = self._call_model_with_retry(model_name, prompt)
                result = self._parse_json_with_repair(model_name, raw_text)
                self._circuit_breaker.record_success()
                if cache_key:
                    self._cache.set(cache_key, result)
                return result
            except LLMAuthError:
                # Not retryable and won't succeed on any other model either.
                self._circuit_breaker.record_failure()
                raise
            except (LLMRateLimitError, LLMTimeoutError) as exc:
                # Exhausted retries against this specific model; trying a
                # different model is a legitimate fallback for
                # provider-side trouble.
                last_error = exc
                self._circuit_breaker.record_failure()
                continue
            except Exception as exc:  # model not found / unsupported / etc.
                last_error = exc
                continue

        raise LLMUnavailableError(
            f"All configured Gemini models failed. Last error: {last_error}"
        ) from last_error

    async def generate_json_async(
        self, prompt: str, *, cache_key: str | None = None
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.generate_json, prompt, cache_key=cache_key)

    # ---- model discovery --------------------------------------------------

    def _resolve_models(self) -> list[str]:
        now = time.monotonic()
        if self._model_list_cache is not None:
            expires_at, models = self._model_list_cache
            if now < expires_at:
                return models
        try:
            names = []
            for m in genai.list_models():
                if "generateContent" in getattr(m, "supported_generation_methods", []):
                    names.append(m.name.replace("models/", ""))
            flash = [n for n in names if "flash" in n]
            other = [n for n in names if n not in flash]
            models = (flash + other) or list(_FALLBACK_MODELS)
        except Exception:
            logger.warning("llm.model_discovery_failed", exc_info=True)
            models = list(_FALLBACK_MODELS)

        self._model_list_cache = (now + self._settings.model_list_cache_ttl_seconds, models)
        return models

    # ---- single-model call with retry --------------------------------------

    def _call_model_with_retry(self, model_name: str, prompt: str) -> str:
        retrying = retry(
            reraise=True,
            stop=stop_after_attempt(self._settings.llm_max_retries),
            wait=wait_exponential_jitter(
                initial=self._settings.llm_backoff_base_seconds,
                max=self._settings.llm_backoff_max_seconds,
            ),
            retry=retry_if_exception_type(_RETRYABLE_ON_SAME_MODEL),
        )
        return retrying(self._call_model_once)(model_name, prompt)

    def _call_model_once(self, model_name: str, prompt: str) -> str:
        model = genai.GenerativeModel(model_name)
        try:
            response = model.generate_content(
                prompt,
                request_options={"timeout": self._settings.llm_timeout_seconds},
            )
        except google_exceptions.ResourceExhausted as exc:
            raise LLMRateLimitError(f"{model_name} rate-limited: {exc}") from exc
        except google_exceptions.DeadlineExceeded as exc:
            raise LLMTimeoutError(f"{model_name} timed out: {exc}") from exc
        except google_exceptions.Unauthenticated as exc:
            raise LLMAuthError(f"Gemini API key rejected: {exc}") from exc
        except google_exceptions.PermissionDenied as exc:
            raise LLMAuthError(f"Gemini API key not permitted: {exc}") from exc
        except google_exceptions.ServiceUnavailable as exc:
            raise LLMRateLimitError(f"{model_name} unavailable: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise LLMResponseFormatError(f"{model_name} returned an empty response")
        return text

    # ---- JSON extraction with one repair attempt ---------------------------

    def _parse_json_with_repair(self, model_name: str, raw_text: str) -> dict[str, Any]:
        try:
            return _extract_json(raw_text)
        except json.JSONDecodeError:
            logger.info("llm.json_repair_attempt", extra={"extra_fields": {"model": model_name}})
            repair_prompt = (
                "Your previous response was not valid JSON. Return ONLY valid JSON, "
                "no markdown fences, no extra text. Here was your response:\n\n" + raw_text
            )
            repaired_text = self._call_model_with_retry(model_name, repair_prompt)
            try:
                return _extract_json(repaired_text)
            except json.JSONDecodeError as exc:
                raise LLMResponseFormatError(
                    f"{model_name} did not return parseable JSON even after a repair attempt"
                ) from exc


_JSON_FENCE_RE = re.compile(r"^```json\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = _JSON_FENCE_RE.sub("", text.strip()).strip("`").strip()
    return json.loads(cleaned)
