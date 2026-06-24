"""Tailored document generation with RAG, ATS critic, and PDF export."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seejob.agents.document_generator import DocumentGenerator
from seejob.core.config import Settings, get_settings
from seejob.core.llm import resolve_document_generator
from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.job import Job
from seejob.models.person import Person
from seejob.models.policy import PolicyConfig
from seejob.services.ats_critic import critique_document
from seejob.services.ingestion import _field_grounded_in_source, _normalize_for_match
from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore
from seejob.services.pdf_export import markdown_to_pdf
from seejob.services.policy import get_policy_config
from seejob.services.profile import get_person
from seejob.services.state_machine import InvalidTransitionError, transition

logger = logging.getLogger(__name__)

MAX_CRITIC_ITERATIONS = 3


class DocumentGenerationError(ValueError):
    """Raised when document generation cannot complete."""


@dataclass
class DocumentGenerationResult:
    """Summary of a document generation run."""

    application_id: int
    documents: list[GeneratedDocument]
    status: ApplicationStatus


def _format_date(value: date | None) -> str:
    if value is None:
        return "present"
    return value.isoformat()


def build_profile_context(
    person: Person,
    *,
    memory_chunks: list[str] | None = None,
) -> str:
    """Serialize verified profile data for LLM grounding."""
    lines = [
        f"Name: {person.full_name}",
        f"Email: {person.email}",
    ]
    if person.phone:
        lines.append(f"Phone: {person.phone}")
    if person.location:
        lines.append(f"Location: {person.location}")
    if person.headline:
        lines.append(f"Headline: {person.headline}")
    if person.summary:
        lines.append(f"Summary: {person.summary}")

    if person.experiences:
        lines.append("\n## Experience (verified)")
        for exp in person.experiences:
            end = "present" if exp.is_current else _format_date(exp.end_date)
            lines.append(
                f"- {exp.title} at {exp.company} "
                f"({_format_date(exp.start_date)} – {end})"
            )
            if exp.description:
                lines.append(f"  {exp.description}")

    if person.education:
        lines.append("\n## Education (verified)")
        for edu in person.education:
            lines.append(
                f"- {edu.degree or 'Degree'} at {edu.institution}"
                + (f", {edu.field_of_study}" if edu.field_of_study else "")
            )

    if person.skills:
        lines.append("\n## Skills (verified)")
        lines.append(", ".join(skill.name for skill in person.skills))

    if memory_chunks:
        lines.append("\n## Relevant memory (supplemental, must not contradict profile)")
        for chunk in memory_chunks:
            lines.append(f"- {chunk[:500]}")

    return "\n".join(lines)


def build_job_context(job: Job) -> str:
    """Serialize job description context."""
    parts = [
        f"Title: {job.title}",
        f"Company: {job.company}",
    ]
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.is_remote:
        parts.append("Remote: yes")
    if job.jd_text:
        parts.append(f"\nJob description:\n{job.jd_text[:12000]}")
    return "\n".join(parts)


def _extract_employer_mentions(markdown: str, profile: Person) -> list[str]:
    """Find employer-like phrases in generated text not in the verified profile."""
    known = {_normalize_for_match(exp.company) for exp in profile.experiences}
    mentions: list[str] = []
    for match in re.finditer(r"(?:at|@)\s+([A-Z][A-Za-z0-9&.,'\- ]{2,40})", markdown):
        candidate = match.group(1).strip().rstrip(".,)")
        norm = _normalize_for_match(candidate)
        if norm and norm not in known and len(norm) > 3:
            mentions.append(candidate)
    return mentions


def validate_document_truthfulness(markdown: str, person: Person) -> list[str]:
    """Check generated document against verified profile — same grounding rules as ingestion."""
    violations: list[str] = []
    profile_context = build_profile_context(person)

    invented = _extract_employer_mentions(markdown, person)
    for employer in invented:
        if not _field_grounded_in_source(employer, profile_context):
            violations.append(f"Possible fabricated employer: {employer}")

    date_patterns = re.findall(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})\b",
        markdown,
        re.IGNORECASE,
    )
    profile_dates = set()
    for exp in person.experiences:
        profile_dates.add(str(exp.start_date.year))
        if exp.end_date:
            profile_dates.add(str(exp.end_date.year))
    for edu in person.education:
        if edu.start_date:
            profile_dates.add(str(edu.start_date.year))
        if edu.end_date:
            profile_dates.add(str(edu.end_date.year))

    for date_str in date_patterns:
        year_match = re.search(r"\d{4}", date_str)
        if year_match and year_match.group() not in profile_dates:
            if not _field_grounded_in_source(date_str, profile_context):
                violations.append(f"Unverified date mention: {date_str}")

    return violations


async def _run_critic_loop(
    generator: DocumentGenerator,
    *,
    doc_type: DocumentType,
    markdown: str,
    profile_context: str,
    job_context: str,
    jd_text: str,
    min_score: float,
) -> tuple[str, float, str, bool]:
    """Run ATS critic with up to MAX_CRITIC_ITERATIONS revision passes."""
    current = markdown
    last_result = critique_document(
        current,
        jd_text=jd_text,
        doc_type=doc_type.value,
        min_score=min_score,
    )

    for iteration in range(MAX_CRITIC_ITERATIONS):
        if last_result.passed:
            break
        if iteration == MAX_CRITIC_ITERATIONS - 1:
            break

        current = await generator.revise_document(
            doc_type=doc_type.value,
            current_markdown=current,
            profile_context=profile_context,
            job_context=job_context,
            revision_notes=last_result.revision_notes,
        )
        last_result = critique_document(
            current,
            jd_text=jd_text,
            doc_type=doc_type.value,
            min_score=min_score,
        )

    return current, last_result.score, last_result.to_report_json(), last_result.passed


async def generate_application_documents(
    db: Session,
    application_id: int,
    person_id: int,
    job_id: int,
    *,
    generator: DocumentGenerator | None = None,
    memory_store: VectorMemoryStore | None = None,
    settings: Settings | None = None,
    policy: PolicyConfig | None = None,
) -> DocumentGenerationResult:
    """Generate CV + cover letter, run ATS critic, compile PDFs, persist rows."""
    cfg = settings or get_settings()
    policy = policy or get_policy_config(db)
    generator = generator or resolve_document_generator(settings=cfg)

    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise DocumentGenerationError(f"Application {application_id} not found")

    person = get_person(db, person_id)
    job = db.get(Job, job_id)
    if job is None:
        raise DocumentGenerationError(f"Job {job_id} not found")

    store = memory_store or VectorMemoryStore(embedder=HashEmbedder())
    jd_text = job.jd_text or f"{job.title} at {job.company}"
    chunks = store.retrieve_relevant(
        person_id,
        jd_text[:4000],
        top_k=5,
        chunk_types=[ChunkType.CV, ChunkType.PROJECT, ChunkType.BEHAVIORAL],
    )
    memory_texts = [c.text for c in chunks]

    profile_context = build_profile_context(person, memory_chunks=memory_texts)
    job_context = build_job_context(job)

    cv_markdown = await generator.generate_cv(
        profile_context=profile_context,
        job_context=job_context,
    )
    cover_markdown = await generator.generate_cover_letter(
        profile_context=profile_context,
        job_context=job_context,
    )

    for label, content in [("CV", cv_markdown), ("Cover letter", cover_markdown)]:
        violations = validate_document_truthfulness(content, person)
        if violations:
            raise DocumentGenerationError(
                f"Truthfulness check failed for {label}: {'; '.join(violations[:3])}"
            )

    min_score = policy.ats_min_score

    cv_markdown, cv_score, cv_report, cv_passed = await _run_critic_loop(
        generator,
        doc_type=DocumentType.CV,
        markdown=cv_markdown,
        profile_context=profile_context,
        job_context=job_context,
        jd_text=jd_text,
        min_score=min_score,
    )
    cover_markdown, cl_score, cl_report, cl_passed = await _run_critic_loop(
        generator,
        doc_type=DocumentType.COVER_LETTER,
        markdown=cover_markdown,
        profile_context=profile_context,
        job_context=job_context,
        jd_text=jd_text,
        min_score=min_score,
    )

    if not cv_passed or not cl_passed:
        raise DocumentGenerationError(
            f"ATS critic did not pass after {MAX_CRITIC_ITERATIONS} iterations "
            f"(cv={cv_score:.2f}, cover={cl_score:.2f}, min={min_score:.2f})"
        )

    cfg.ensure_directories()
    doc_dir = cfg.documents_dir / f"app_{application_id}"
    doc_dir.mkdir(parents=True, exist_ok=True)

    cv_pdf = markdown_to_pdf(cv_markdown, doc_dir / "cv.pdf")
    cl_pdf = markdown_to_pdf(cover_markdown, doc_dir / "cover_letter.pdf")

    for existing in list(app.documents):
        db.delete(existing)
    db.flush()

    cv_doc = GeneratedDocument(
        application_id=application_id,
        doc_type=DocumentType.CV,
        markdown_content=cv_markdown,
        pdf_path=str(cv_pdf),
        ats_score=cv_score,
        critic_report=cv_report,
        version=1,
        approved=False,
    )
    cl_doc = GeneratedDocument(
        application_id=application_id,
        doc_type=DocumentType.COVER_LETTER,
        markdown_content=cover_markdown,
        pdf_path=str(cl_pdf),
        ats_score=cl_score,
        critic_report=cl_report,
        version=1,
        approved=False,
    )
    db.add_all([cv_doc, cl_doc])
    db.commit()
    db.refresh(cv_doc)
    db.refresh(cl_doc)

    return DocumentGenerationResult(
        application_id=application_id,
        documents=[cv_doc, cl_doc],
        status=ApplicationStatus.DOCS_READY,
    )


def queue_document_generation(db: Session, application_id: int) -> DocumentGenerationResult:
    """Synchronous entry point for workers — transition, generate, finalize."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise DocumentGenerationError(f"Application {application_id} not found")

    if app.status == ApplicationStatus.PENDING_APPROVAL:
        app.status = transition(app.status, ApplicationStatus.GENERATING_DOCS)
        db.commit()
    elif app.status != ApplicationStatus.GENERATING_DOCS:
        raise DocumentGenerationError(
            f"Application must be pending_approval or generating_docs "
            f"(current: {app.status.value})"
        )

    try:
        result = asyncio.run(
            generate_application_documents(
                db,
                application_id,
                app.person_id,
                app.job_id,
            )
        )
        app.status = transition(app.status, ApplicationStatus.DOCS_READY)
        app.status_message = "Documents generated and ready for review"
        db.commit()
        return result
    except DocumentGenerationError as exc:
        logger.exception("Document generation failed for application %s", application_id)
        try:
            app.status = transition(app.status, ApplicationStatus.FAILED)
            app.status_message = str(exc)[:500]
            db.commit()
        except InvalidTransitionError:
            db.rollback()
        raise


def on_job_approved_queue_docs(
    db: Session,
    application: Application,
    *,
    policy: PolicyConfig,
) -> DocumentGenerationResult | None:
    """Worker hook: queue doc generation when job approved and auto_apply is off.

    Callable from services or workers (not a daemon). Expects application at
    pending_approval after job review approval.
    """
    if policy.auto_apply:
        return None
    if application.status != ApplicationStatus.PENDING_APPROVAL:
        return None
    return queue_document_generation(db, application.id)
