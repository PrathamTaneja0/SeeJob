"""Profile ingestion — parse CV files, extract structure, seed vector memory."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import httpx
from docx import Document
from pypdf import PdfReader
from sqlalchemy.orm import Session

from seejob.agents.profile_extractor import (
    ExtractedProfile,
    OpenAIProfileExtractor,
    ProfileExtractor,
    parse_optional_date,
)
from seejob.models.person import Education, Experience, Person, Skill
from seejob.services.memory import ChunkType, VectorMemoryStore
from seejob.services.profile import get_person
from seejob.services.qa import seed_behavioral_templates

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


@dataclass
class IngestionResult:
    """Summary of an ingestion run."""

    person_id: int
    raw_text_length: int
    chunks_stored: int
    experiences_added: int = 0
    education_added: int = 0
    skills_added: int = 0
    fields_updated: list[str] = field(default_factory=list)
    project_chunks: int = 0
    behavioral_chunks: int = 0


@dataclass
class LinkImportResult:
    """Summary of link import."""

    person_id: int
    sources_fetched: list[str] = field(default_factory=list)
    chunks_stored: int = 0
    errors: list[str] = field(default_factory=list)


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags and collect visible text."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return re.sub(r"\n{3,}", "\n\n", parser.get_text())


def parse_pdf(content: bytes) -> str:
    """Extract text from a PDF file."""
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def parse_docx(content: bytes) -> str:
    """Extract text from a DOCX file."""
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_upload(content: bytes, filename: str) -> str:
    """Parse uploaded file content into plain text."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(content)
    if suffix in {".docx", ".doc"}:
        return parse_docx(content)
    if suffix == ".txt":
        return content.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix}. Use PDF, DOCX, or TXT.")


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks for vector storage."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _apply_extracted_person_fields(person: Person, extracted: ExtractedProfile) -> list[str]:
    """Update scalar person fields from extraction when currently empty."""
    updated: list[str] = []
    field_map = {
        "full_name": extracted.full_name,
        "email": extracted.email,
        "phone": extracted.phone,
        "location": extracted.location,
        "headline": extracted.headline,
        "summary": extracted.summary,
        "linkedin_url": extracted.linkedin_url,
        "github_url": extracted.github_url,
        "portfolio_url": extracted.portfolio_url,
    }
    for attr, value in field_map.items():
        if value and not getattr(person, attr):
            setattr(person, attr, value)
            updated.append(attr)
    return updated


def _persist_extracted_entities(
    db: Session,
    person: Person,
    extracted: ExtractedProfile,
) -> tuple[int, int, int]:
    """Insert extracted experiences, education, and skills."""
    exp_count = 0
    for item in extracted.experiences:
        start = parse_optional_date(item.start_date)
        if not start:
            logger.warning("Skipping experience without start_date: %s", item.company)
            continue
        db.add(
            Experience(
                person_id=person.id,
                company=item.company,
                title=item.title,
                location=item.location,
                start_date=start,
                end_date=parse_optional_date(item.end_date),
                is_current=item.is_current,
                description=item.description,
            )
        )
        exp_count += 1

    edu_count = 0
    for item in extracted.education:
        db.add(
            Education(
                person_id=person.id,
                institution=item.institution,
                degree=item.degree,
                field_of_study=item.field_of_study,
                start_date=parse_optional_date(item.start_date),
                end_date=parse_optional_date(item.end_date),
                gpa=item.gpa,
            )
        )
        edu_count += 1

    skill_count = 0
    existing_names = {s.name.lower() for s in person.skills}
    for item in extracted.skills:
        if item.name.lower() in existing_names:
            continue
        db.add(
            Skill(
                person_id=person.id,
                name=item.name,
                level=item.level,
                years=item.years,
            )
        )
        existing_names.add(item.name.lower())
        skill_count += 1

    return exp_count, edu_count, skill_count


async def ingest_cv(
    db: Session,
    person_id: int,
    content: bytes,
    filename: str,
    *,
    extractor: ProfileExtractor | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> IngestionResult:
    """Parse CV, extract structured fields, chunk text, and seed memory."""
    person = get_person(db, person_id)
    raw_text = parse_upload(content, filename)

    if not raw_text.strip():
        raise ValueError("No text could be extracted from the uploaded file")

    ext = extractor or OpenAIProfileExtractor()
    try:
        extraction = await ext.extract(raw_text)
    except ValueError:
        from seejob.agents.profile_extractor import MockProfileExtractor

        extraction = await MockProfileExtractor().extract(raw_text)

    extracted = extraction.profile
    fields_updated = _apply_extracted_person_fields(person, extracted)
    exp_added, edu_added, skill_added = _persist_extracted_entities(db, person, extracted)
    db.commit()

    store = memory_store or VectorMemoryStore()
    cv_chunks = chunk_text(raw_text)
    chunks_stored = store.add_chunks(person_id, cv_chunks, chunk_type=ChunkType.CV)

    project_chunks = 0
    if extracted.project_descriptions:
        project_chunks = store.add_chunks(
            person_id,
            extracted.project_descriptions,
            chunk_type=ChunkType.PROJECT,
        )
        chunks_stored += project_chunks

    behavioral_chunks = 0
    if extracted.behavioral_stories:
        behavioral_chunks = store.add_chunks(
            person_id,
            extracted.behavioral_stories,
            chunk_type=ChunkType.BEHAVIORAL,
        )
        chunks_stored += behavioral_chunks

    seed_behavioral_templates(db, person_id)

    return IngestionResult(
        person_id=person_id,
        raw_text_length=len(raw_text),
        chunks_stored=chunks_stored,
        experiences_added=exp_added,
        education_added=edu_added,
        skills_added=skill_added,
        fields_updated=fields_updated,
        project_chunks=project_chunks,
        behavioral_chunks=behavioral_chunks,
    )


async def ingest_text(
    db: Session,
    person_id: int,
    text: str,
    *,
    source: str = "manual",
    extractor: ProfileExtractor | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> IngestionResult:
    """Ingest pasted plain text (manual fallback for link import)."""
    return await ingest_cv(
        db,
        person_id,
        text.encode("utf-8"),
        "pasted.txt",
        extractor=extractor,
        memory_store=memory_store,
    )


async def fetch_url_text(url: str, *, timeout: float = 15.0) -> str:
    """Fetch public URL and extract visible text."""
    headers = {
        "User-Agent": "SeeJob/0.1 (profile import; +https://github.com/seejob)",
        "Accept": "text/html,application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type and "api.github.com" in url:
            return _format_github_api(response.json())

        return extract_text_from_html(response.text)


def _format_github_api(data: dict) -> str:
    """Format GitHub API user response as profile text."""
    parts = [
        f"Name: {data.get('name') or data.get('login', '')}",
        f"Bio: {data.get('bio') or ''}",
        f"Location: {data.get('location') or ''}",
        f"Company: {data.get('company') or ''}",
        f"Blog: {data.get('blog') or ''}",
    ]
    return "\n".join(p for p in parts if p.split(": ", 1)[-1])


def _github_api_url(url: str) -> str | None:
    """Convert github.com profile URL to API URL."""
    match = re.match(r"https?://(?:www\.)?github\.com/([^/?#]+)/?", url, re.I)
    if match:
        return f"https://api.github.com/users/{match.group(1)}"
    return None


async def import_profile_links(
    db: Session,
    person_id: int,
    *,
    memory_store: VectorMemoryStore | None = None,
) -> LinkImportResult:
    """Fetch public LinkedIn/GitHub text from person URLs and store in memory."""
    person = get_person(db, person_id)
    store = memory_store or VectorMemoryStore()
    result = LinkImportResult(person_id=person_id)

    urls: list[tuple[str, ChunkType]] = []
    if person.linkedin_url:
        urls.append((person.linkedin_url, ChunkType.LINKEDIN))
    if person.github_url:
        urls.append((person.github_url, ChunkType.GITHUB))

    if not urls:
        result.errors.append("No linkedin_url or github_url set on profile")
        return result

    for url, chunk_type in urls:
        fetch_url = _github_api_url(url) or url
        try:
            text = await fetch_url_text(fetch_url)
            if not text.strip():
                result.errors.append(f"No text extracted from {url}")
                continue
            chunks = chunk_text(text)
            stored = store.add_chunks(person_id, chunks, chunk_type=chunk_type)
            result.chunks_stored += stored
            result.sources_fetched.append(url)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            result.errors.append(f"Failed to fetch {url}: {exc}")

    return result
