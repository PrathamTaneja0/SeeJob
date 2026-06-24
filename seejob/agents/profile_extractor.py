"""LLM-assisted structured profile extraction from raw CV text."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a CV parsing assistant. Extract ONLY information explicitly stated in the document.

Rules:
- Do NOT invent employers, job titles, dates, degrees, or skills.
- If a field is missing or unclear, use null or omit it.
- Dates must be ISO format YYYY-MM-DD when possible; use null if only year is given.
- Return valid JSON matching the schema exactly.
"""


class ExtractedExperience(BaseModel):
    """Experience entry extracted from CV text."""

    company: str
    title: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None


class ExtractedEducation(BaseModel):
    """Education entry extracted from CV text."""

    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None


class ExtractedSkill(BaseModel):
    """Skill extracted from CV text."""

    name: str
    level: str | None = None
    years: float | None = None


class ExtractedProfile(BaseModel):
    """Structured profile fields extracted from unstructured CV text."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    project_descriptions: list[str] = Field(default_factory=list)
    behavioral_stories: list[str] = Field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of profile extraction."""

    profile: ExtractedProfile
    raw_response: str = ""
    model: str = ""


class ProfileExtractor(ABC):
    """Interface for LLM-assisted CV extraction."""

    @abstractmethod
    async def extract(self, cv_text: str) -> ExtractionResult:
        """Extract structured profile data from raw CV text."""


def parse_optional_date(value: str | None) -> date | None:
    """Parse ISO date string; return None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class OpenAIProfileExtractor(ProfileExtractor):
    """Extract profile fields via an OpenAI-compatible chat completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def extract(self, cv_text: str) -> ExtractionResult:
        """Call LLM with JSON schema instructions."""
        if not self._settings.openai_api_key:
            raise ValueError("SEEJOB_OPENAI_API_KEY is required for LLM extraction")

        schema = ExtractedProfile.model_json_schema()
        user_prompt = (
            "Extract structured profile data from this CV/resume text.\n\n"
            f"JSON schema:\n{json.dumps(schema, indent=2)}\n\n"
            f"CV TEXT:\n{cv_text[:50000]}"
        )

        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._settings.openai_base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = ExtractedProfile.model_validate_json(content)
        return ExtractionResult(
            profile=parsed,
            raw_response=content,
            model=self._settings.llm_model,
        )


class MockProfileExtractor(ProfileExtractor):
    """Deterministic extractor for tests — parses a minimal JSON block if present."""

    def __init__(self, fixed_profile: ExtractedProfile | None = None) -> None:
        self._fixed_profile = fixed_profile

    async def extract(self, cv_text: str) -> ExtractionResult:
        if self._fixed_profile is not None:
            return ExtractionResult(profile=self._fixed_profile, model="mock")

        profile = ExtractedProfile(
            full_name="Jane Doe",
            email="jane@example.com",
            summary=cv_text[:500] if cv_text else None,
            experiences=[
                ExtractedExperience(
                    company="Acme Corp",
                    title="Software Engineer",
                    start_date="2020-01-01",
                    is_current=True,
                    description="Built backend services.",
                )
            ],
            skills=[ExtractedSkill(name="Python"), ExtractedSkill(name="FastAPI")],
        )
        return ExtractionResult(profile=profile, model="mock")
