"""Typed domain objects.

These replace the original code's pattern of passing raw ``dict``s around
and reading them with ``.get(...)`` at render time. Parsing happens once,
at the boundary with the LLM response, and produces a validated object --
or raises ``ValueError`` (wrapped by the service layer into
``LLMResponseFormatError``) with a clear reason, instead of the UI
silently rendering empty sections when a field is missing or the wrong
type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"expected string field '{key}', got {type(value).__name__}")
    return value


def _require_int(data: Mapping[str, Any], key: str, *, lo: int, hi: int) -> int:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"expected numeric field '{key}', got {type(value).__name__}")
    return max(lo, min(hi, int(value)))


def _string_list(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"expected list field '{key}', got {type(value).__name__}")
    return [str(item) for item in value]


@dataclass(frozen=True)
class ResumeOptimizationResult:
    match_score: int
    missing_keywords: list[str]
    strengths: list[str]
    improvement_suggestions: list[str]
    optimized_resume: str
    cover_letter: str

    @classmethod
    def from_llm_dict(cls, data: Mapping[str, Any]) -> "ResumeOptimizationResult":
        return cls(
            match_score=_require_int(data, "match_score", lo=0, hi=100),
            missing_keywords=_string_list(data, "missing_keywords"),
            strengths=_string_list(data, "strengths"),
            improvement_suggestions=_string_list(data, "improvement_suggestions"),
            optimized_resume=_require_str(data, "optimized_resume"),
            cover_letter=_require_str(data, "cover_letter"),
        )


@dataclass(frozen=True)
class LinkedInOptimizationResult:
    headline: str
    about_section: str
    experience_bullets: list[str]
    skills_to_add: list[str]
    improvement_notes: list[str]

    @classmethod
    def from_llm_dict(cls, data: Mapping[str, Any]) -> "LinkedInOptimizationResult":
        return cls(
            headline=_require_str(data, "headline"),
            about_section=_require_str(data, "about_section"),
            experience_bullets=_string_list(data, "experience_bullets"),
            skills_to_add=_string_list(data, "skills_to_add"),
            improvement_notes=_string_list(data, "improvement_notes"),
        )


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    source_filename: str
    char_count: int
    truncated: bool


@dataclass(frozen=True)
class FetchedContent:
    text: str
    source_url: str
    truncated: bool
    blocked: bool = False
    block_reason: str = ""
