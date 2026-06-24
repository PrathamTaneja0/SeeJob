"""LLM document generation for tailored CV and cover letters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TRUTHFULNESS_SYSTEM_PROMPT = """You are a professional resume writer helping tailor application documents.

STRICT RULES — violations are unacceptable:
- Use ONLY employers, job titles, dates, degrees, institutions, and skills from the provided profile.
- Do NOT invent, embellish, or infer experience, projects, metrics, or achievements not in the profile.
- Do NOT add employers or employment dates that are not in the profile.
- Tailor emphasis and wording to the job description using existing facts only.
- Output valid Markdown only (no code fences wrapping the document).
- CV: use clear headings (## Experience, ## Education, ## Skills), bullet points, 1-2 pages equivalent.
- Cover letter: professional tone, 3-4 paragraphs, reference the role and company from the JD.
"""


class DocumentGenerator(ABC):
    """Interface for generating tailored application documents."""

    @abstractmethod
    async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
        """Generate a tailored CV in Markdown."""

    @abstractmethod
    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        """Generate a tailored cover letter in Markdown."""

    @abstractmethod
    async def revise_document(
        self,
        *,
        doc_type: str,
        current_markdown: str,
        profile_context: str,
        job_context: str,
        revision_notes: str,
    ) -> str:
        """Revise a document based on ATS critic feedback."""


class OpenAIDocumentGenerator(DocumentGenerator):
    """Generate documents via OpenAI-compatible chat API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def _chat(self, user_prompt: str) -> str:
        if not self._settings.openai_api_key:
            raise ValueError("SEEJOB_OPENAI_API_KEY is required for document generation")

        payload = {
            "model": self._settings.llm_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": TRUTHFULNESS_SYSTEM_PROMPT},
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

        return data["choices"][0]["message"]["content"].strip()

    async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
        prompt = (
            "Write a tailored CV in Markdown for this job.\n\n"
            f"Job context:\n{job_context[:8000]}\n\n"
            f"Verified profile (use ONLY this data):\n{profile_context[:12000]}"
        )
        return await self._chat(prompt)

    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        prompt = (
            "Write a tailored cover letter in Markdown for this job.\n\n"
            f"Job context:\n{job_context[:8000]}\n\n"
            f"Verified profile (use ONLY this data):\n{profile_context[:12000]}"
        )
        return await self._chat(prompt)

    async def revise_document(
        self,
        *,
        doc_type: str,
        current_markdown: str,
        profile_context: str,
        job_context: str,
        revision_notes: str,
    ) -> str:
        prompt = (
            f"Revise this {doc_type} based on ATS feedback. Keep all facts grounded in the profile.\n\n"
            f"Revision notes:\n{revision_notes}\n\n"
            f"Current document:\n{current_markdown[:10000]}\n\n"
            f"Job context:\n{job_context[:4000]}\n\n"
            f"Verified profile:\n{profile_context[:8000]}"
        )
        return await self._chat(prompt)


class MockDocumentGenerator(DocumentGenerator):
    """Deterministic generator for tests."""

    revision_count: int = 0

    async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
        return (
            f"# Jane Applicant\n\n"
            f"## Experience\n\n"
            f"- Software Engineer at Acme Corp (from profile)\n\n"
            f"## Skills\n\n"
            f"- Python\n- FastAPI\n\n"
            f"<!-- profile_len={len(profile_context)} jd_len={len(job_context)} -->"
        )

    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        return (
            f"Dear Hiring Manager,\n\n"
            f"I am excited to apply for this role. My experience at Acme Corp aligns with your needs.\n\n"
            f"Sincerely,\nJane Applicant"
        )

    async def revise_document(
        self,
        *,
        doc_type: str,
        current_markdown: str,
        profile_context: str,
        job_context: str,
        revision_notes: str,
    ) -> str:
        MockDocumentGenerator.revision_count += 1
        return (
            f"{current_markdown}\n\n"
            f"## ATS Revision\n\n"
            f"- Addressed: {revision_notes[:200]}\n"
            f"- Keywords from JD integrated\n"
        )
