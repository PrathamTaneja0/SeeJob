"""LLM document generation for tailored CV and cover letters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from seejob.core.config import Settings, get_settings
from seejob.services.ats_critic import extract_jd_keywords

logger = logging.getLogger(__name__)

TRUTHFULNESS_SYSTEM_PROMPT = """You are a professional resume writer helping tailor application documents.

STRICT RULES — violations are unacceptable:
- Use ONLY employers, job titles, dates, degrees, institutions, and skills from the provided profile.
- Do NOT invent, embellish, or infer experience, projects, metrics, or achievements not in the profile.
- Do NOT add employers or employment dates that are not in the profile.
- Tailor emphasis and wording to the job description using existing facts only.
- Output valid Markdown only (no code fences wrapping the document, no HTML comments).
- CV: use clear headings (## Experience, ## Education, ## Skills), bullet points, 1-2 pages equivalent.
- Cover letter: professional tone, 3-4 paragraphs, reference the role and company from the JD.
- Do NOT append ATS critique notes, revision logs, or meta-commentary to the document body.
"""

_CV_USER_PROMPT = """Write a tailored CV in Markdown for this job application.

Requirements:
- Start with a single # heading using the candidate's real name from the profile.
- Include contact line (email, phone, location) when available in the profile.
- Use ## Experience, ## Education, and ## Skills sections (add ## Summary only if profile has a summary).
- Under Experience, expand each verified role with 2-4 bullet points drawn from profile descriptions.
- Mirror important job-description keywords in bullets only where they truthfully match profile skills/experience.
- Professional tone; aim for 1-2 pages of content (~800-2500 words).
- Use supplemental memory chunks only when they do not contradict verified profile data.

Job context:
{job_context}

Verified profile (use ONLY this data):
{profile_context}
"""

_COVER_LETTER_USER_PROMPT = """Write a tailored cover letter in Markdown for this job application.

Requirements:
- Open with a professional greeting; reference the specific role title and company from the job context.
- 3-4 paragraphs connecting verified profile experience to JD requirements.
- Use keywords from the job description only where they match real profile facts.
- Close with a professional sign-off using the candidate's real name.
- No HTML comments or revision notes in the output.

Job context:
{job_context}

Verified profile (use ONLY this data):
{profile_context}
"""

_REVISE_USER_PROMPT = """Revise this {doc_type} based on ATS feedback. Keep all facts grounded in the profile.

Rules:
- Return the full revised document only — no preamble, no "## ATS Revision" section, no meta notes.
- Integrate missing JD keywords naturally in existing bullets where truthful.
- Preserve Markdown headings and professional tone.

ATS revision notes:
{revision_notes}

Current document:
{current_markdown}

Job context:
{job_context}

Verified profile:
{profile_context}
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
        prompt = _CV_USER_PROMPT.format(
            job_context=job_context[:8000],
            profile_context=profile_context[:12000],
        )
        return await self._chat(prompt)

    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        prompt = _COVER_LETTER_USER_PROMPT.format(
            job_context=job_context[:8000],
            profile_context=profile_context[:12000],
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
        prompt = _REVISE_USER_PROMPT.format(
            doc_type=doc_type,
            revision_notes=revision_notes[:4000],
            current_markdown=current_markdown[:10000],
            job_context=job_context[:4000],
            profile_context=profile_context[:8000],
        )
        return await self._chat(prompt)


def _parse_profile_field(profile_context: str, prefix: str) -> str | None:
    for line in profile_context.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def _parse_section_bullets(profile_context: str, header: str) -> list[str]:
    lines = profile_context.splitlines()
    in_section = False
    bullets: list[str] = []
    for line in lines:
        if line.startswith(header):
            in_section = True
            continue
        if in_section:
            if line.startswith("## ") and not line.startswith(header):
                break
            stripped = line.strip()
            if stripped.startswith("- "):
                bullets.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("  "):
                bullets.append(stripped)
    return bullets


def _parse_skills(profile_context: str) -> list[str]:
    lines = profile_context.splitlines()
    in_section = False
    skills: list[str] = []
    for line in lines:
        if line.startswith("## Skills"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.strip():
                skills.extend(s.strip() for s in line.split(",") if s.strip())
    return skills


def _parse_job_title(job_context: str) -> str:
    return _parse_profile_field(job_context, "Title: ") or "the role"


def _parse_job_company(job_context: str) -> str:
    return _parse_profile_field(job_context, "Company: ") or "your company"


def _jd_text_from_context(job_context: str) -> str:
    marker = "Job description:"
    idx = job_context.find(marker)
    if idx >= 0:
        return job_context[idx + len(marker) :].strip()
    return job_context


def _build_mock_cv(
    *,
    profile_context: str,
    job_context: str,
    extra_keywords: list[str] | None = None,
) -> str:
    """Build a realistic CV from parsed profile + JD keywords (mock/test only)."""
    name = _parse_profile_field(profile_context, "Name: ") or "Applicant"
    email = _parse_profile_field(profile_context, "Email: ")
    phone = _parse_profile_field(profile_context, "Phone: ")
    location = _parse_profile_field(profile_context, "Location: ")
    headline = _parse_profile_field(profile_context, "Headline: ")
    summary = _parse_profile_field(profile_context, "Summary: ")

    contact_parts = [p for p in (email, phone, location) if p]
    contact_line = " · ".join(contact_parts)

    jd_keywords = extract_jd_keywords(_jd_text_from_context(job_context), max_keywords=12)
    if extra_keywords:
        for kw in extra_keywords:
            if kw not in jd_keywords:
                jd_keywords.append(kw)

    experiences = _parse_section_bullets(profile_context, "## Experience")
    education = _parse_section_bullets(profile_context, "## Education")
    skills = _parse_skills(profile_context)

    lines = [f"# {name}"]
    if contact_line:
        lines.append(contact_line)
    if headline:
        lines.append("")
        lines.append(f"*{headline}*")

    if summary:
        lines.extend(["", "## Summary", "", summary])

    lines.extend(["", "## Experience", ""])
    if experiences:
        for exp in experiences:
            lines.append(f"- {exp}")
    else:
        lines.append("- See verified profile for experience details")

    lines.extend(["", "## Education", ""])
    if education:
        for edu in education:
            lines.append(f"- {edu}")
    else:
        lines.append("- See verified profile for education details")

    lines.extend(["", "## Skills", ""])
    skill_items = list(dict.fromkeys(skills + [kw.title() for kw in jd_keywords[:10]]))
    if skill_items:
        for skill in skill_items[:20]:
            lines.append(f"- {skill}")
    else:
        lines.append("- See verified profile for skills")

    return "\n".join(lines)


def _build_mock_cover_letter(*, profile_context: str, job_context: str) -> str:
    name = _parse_profile_field(profile_context, "Name: ") or "Applicant"
    title = _parse_job_title(job_context)
    company = _parse_job_company(job_context)
    experiences = _parse_section_bullets(profile_context, "## Experience")
    skills = _parse_skills(profile_context)
    exp_phrase = experiences[0] if experiences else "my verified professional background"
    skill_phrase = ", ".join(skills[:5]) if skills else "relevant technical skills"
    jd_keywords = extract_jd_keywords(_jd_text_from_context(job_context), max_keywords=10)
    keyword_phrase = ", ".join(jd_keywords[:8]) if jd_keywords else skill_phrase

    return (
        f"## Cover Letter\n\n"
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my interest in the {title} position at {company}. "
        f"My background includes {exp_phrase}, with hands-on experience in {skill_phrase}. "
        f"I am well prepared to contribute across {keyword_phrase} as described in your posting.\n\n"
        f"I would welcome the opportunity to contribute to {company} and discuss how my "
        f"verified qualifications support this role.\n\n"
        f"Sincerely,\n{name}"
    )


class MockDocumentGenerator(DocumentGenerator):
    """Deterministic generator for tests — builds realistic structure from profile + JD."""

    revision_count: int = 0

    async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
        return _build_mock_cv(profile_context=profile_context, job_context=job_context)

    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        return _build_mock_cover_letter(profile_context=profile_context, job_context=job_context)

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
        jd_text = _jd_text_from_context(job_context)
        missing = extract_jd_keywords(jd_text, max_keywords=15)
        content_lower = current_markdown.lower()
        extra = [kw for kw in missing if kw not in content_lower][:8]

        if doc_type == "cv":
            revised = _build_mock_cv(
                profile_context=profile_context,
                job_context=job_context,
                extra_keywords=extra,
            )
            if extra:
                lines = revised.splitlines()
                skills_idx = next(
                    (i for i, line in enumerate(lines) if line.strip() == "## Skills"),
                    len(lines),
                )
                for kw in extra:
                    if not any(kw.lower() in line.lower() for line in lines):
                        lines.insert(skills_idx + 2, f"- {kw.title()}")
                revised = "\n".join(lines)
            return revised

        name = _parse_profile_field(profile_context, "Name: ") or "Applicant"
        title = _parse_job_title(job_context)
        company = _parse_job_company(job_context)
        keyword_phrase = ", ".join(extra[:8]) if extra else "the required qualifications"
        return (
            f"## Cover Letter\n\n"
            f"Dear Hiring Manager,\n\n"
            f"I am excited to apply for the {title} role at {company}. "
            f"My verified experience aligns with your needs in {keyword_phrase}.\n\n"
            f"I would welcome the opportunity to discuss how my background supports your team.\n\n"
            f"Sincerely,\n{name}"
        )
