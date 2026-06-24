"""Tests for document generation, ATS critic, PDF export, and approval gates."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from seejob.agents.document_generator import DocumentGenerator, MockDocumentGenerator
from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.job import Job, JobStatus
from seejob.models.person import Experience, Person, Skill, WorkAuthorization
from seejob.models.policy import PolicyConfig
from seejob.services.ats_critic import critique_document
from seejob.services.documents import (
    DocumentGenerationError,
    build_profile_context,
    generate_application_documents,
    queue_document_generation,
    validate_document_truthfulness,
)
from seejob.services.pdf_export import markdown_to_pdf


SAMPLE_JD = """
Senior Python Engineer at Acme Corp.
Requirements: Python, FastAPI, software engineering, APIs, backend development.
Experience building scalable services with Python and FastAPI required.
"""


class FailingThenPassGenerator(DocumentGenerator):
    """Mock that fails ATS on first attempt, passes after revision."""

    def __init__(self) -> None:
        self.attempts = 0

    async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
        return "Short cv without headings or keywords."

    async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
        return "Brief letter."

    async def revise_document(
        self,
        *,
        doc_type: str,
        current_markdown: str,
        profile_context: str,
        job_context: str,
        revision_notes: str,
    ) -> str:
        self.attempts += 1
        if doc_type == "cv":
            return (
                "# Jane Applicant\n\n## Experience\n\n"
                "- Python and FastAPI software engineer at Acme Corp\n"
                "- Backend development and scalable APIs\n\n"
                "## Skills\n\n- Python\n- FastAPI\n- software\n- engineering\n- APIs\n"
            )
        return (
            "Dear Hiring Manager,\n\n"
            "I bring Python, FastAPI, and software engineering experience from Acme Corp "
            "building scalable backend APIs.\n\n"
            "Sincerely,\nJane"
        )


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": False,
        "require_doc_approval": True,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "ats_min_score": 0.5,
        "daily_apply_limit": 10,
        "rate_limits_json": '{"default": 10}',
        "blocked_companies_json": "[]",
        "blocked_keywords_json": "[]",
        "sourcing_enabled": True,
        "sourcing_schedule": "0 8 * * *",
    }
    defaults.update(overrides)
    policy = PolicyConfig(**defaults)
    db_session.add(policy)
    db_session.commit()
    return policy


def _seed_pipeline(db_session) -> tuple[Application, Person, Job]:
    person = Person(
        full_name="Jane Applicant",
        email="jane@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    db_session.add(person)
    db_session.flush()

    db_session.add(
        Experience(
            person_id=person.id,
            company="Acme Corp",
            title="Software Engineer",
            start_date=date(2020, 1, 1),
            is_current=True,
            description="Built APIs with Python and FastAPI.",
        )
    )
    db_session.add(Skill(person_id=person.id, name="Python"))
    db_session.add(Skill(person_id=person.id, name="FastAPI"))

    job = Job(
        url="https://example.com/jobs/python",
        title="Python Engineer",
        company="Acme Corp",
        source="test",
        status=JobStatus.REVIEWED,
        jd_text=SAMPLE_JD,
    )
    db_session.add(job)
    db_session.flush()

    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=ApplicationStatus.PENDING_APPROVAL,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    db_session.refresh(person)
    db_session.refresh(job)
    return app, person, job


@pytest.mark.asyncio
async def test_generate_application_documents_creates_pdf_and_rows(
    db_session, tmp_path, monkeypatch
) -> None:
    """Document generation stores markdown, ATS scores, and PDF files."""
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session)
    app, person, job = _seed_pipeline(db_session)
    generator = MockDocumentGenerator()

    result = await generate_application_documents(
        db_session,
        app.id,
        person.id,
        job.id,
        generator=generator,
        settings=get_settings(),
    )

    assert len(result.documents) == 2
    assert all(doc.ats_score is not None for doc in result.documents)
    assert all(doc.approved is False for doc in result.documents)
    assert all(doc.pdf_path and Path(doc.pdf_path).exists() for doc in result.documents)

    types = {doc.doc_type for doc in result.documents}
    assert types == {DocumentType.CV, DocumentType.COVER_LETTER}


@pytest.mark.asyncio
async def test_critic_revision_loop(db_session, tmp_path, monkeypatch) -> None:
    """ATS critic triggers revision until documents pass threshold."""
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session, ats_min_score=0.5)
    app, person, job = _seed_pipeline(db_session)
    generator = FailingThenPassGenerator()

    result = await generate_application_documents(
        db_session,
        app.id,
        person.id,
        job.id,
        generator=generator,
        settings=get_settings(),
    )

    assert generator.attempts >= 1
    assert all(doc.ats_score is not None for doc in result.documents)


def test_critique_document_pass_and_fail() -> None:
    """ATS critic scores keyword coverage and format."""
    good = critique_document(
        (
            "# Name\n\n## Experience\n\n"
            "- Senior Python FastAPI software engineer\n"
            "- Backend development with scalable APIs at Acme Corp\n"
        ),
        jd_text=SAMPLE_JD,
        doc_type="cv",
        min_score=0.35,
    )
    assert good.passed
    assert good.score >= 0.35

    bad = critique_document(
        "no structure here",
        jd_text=SAMPLE_JD,
        doc_type="cv",
        min_score=0.7,
    )
    assert not bad.passed
    assert bad.issues


def test_validate_document_truthfulness_flags_unknown_employer(db_session) -> None:
    """Truthfulness check rejects fabricated employers."""
    person = Person(
        full_name="Jane",
        email="jane@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    db_session.add(person)
    db_session.flush()
    db_session.add(
        Experience(
            person_id=person.id,
            company="Acme Corp",
            title="Engineer",
            start_date=date(2020, 1, 1),
            is_current=True,
        )
    )
    db_session.commit()

    violations = validate_document_truthfulness(
        "Worked at FakeCorp Industries as CTO since 2019.",
        person,
    )
    assert violations


def test_build_profile_context_includes_verified_experience(db_session) -> None:
    """Profile context serializes structured data for LLM grounding."""
    person = Person(
        full_name="Jane",
        email="jane@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    db_session.add(person)
    db_session.flush()
    db_session.add(
        Experience(
            person_id=person.id,
            company="Acme Corp",
            title="Engineer",
            start_date=date(2020, 1, 1),
            is_current=True,
        )
    )
    db_session.commit()

    context = build_profile_context(person)
    assert "Acme Corp" in context
    assert "Engineer" in context


def test_markdown_to_pdf_creates_file(tmp_path) -> None:
    """PDF compiler writes an ATS-friendly file."""
    output = tmp_path / "cv.pdf"
    markdown_to_pdf("# Jane\n\n## Skills\n\n- Python\n", output)
    assert output.exists()
    assert output.stat().st_size > 0


def test_queue_document_generation_transitions_to_docs_ready(
    db_session, tmp_path, monkeypatch
) -> None:
    """Queue helper transitions pending_approval → docs_ready."""
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "true")
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session, ats_min_score=0.5)
    app, _, _ = _seed_pipeline(db_session)

    result = queue_document_generation(db_session, app.id)
    db_session.refresh(app)

    assert app.status == ApplicationStatus.DOCS_READY
    assert len(result.documents) == 2


def test_generate_documents_api(client, db_session, tmp_path, monkeypatch) -> None:
    """POST /generate triggers document generation."""
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "true")
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session, ats_min_score=0.5)
    app, _, _ = _seed_pipeline(db_session)

    response = client.post(f"/api/v1/applications/{app.id}/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "docs_ready"
    assert len(data["documents"]) == 2


def test_get_documents_preview(client, db_session) -> None:
    """GET /documents returns markdown and ATS report."""
    _seed_policy(db_session)
    app, _, _ = _seed_pipeline(db_session)
    doc = GeneratedDocument(
        application_id=app.id,
        doc_type=DocumentType.CV,
        markdown_content="# CV",
        ats_score=0.85,
        critic_report='{"score": 0.85}',
        approved=False,
    )
    db_session.add(doc)
    db_session.commit()

    response = client.get(f"/api/v1/applications/{app.id}/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["application_id"] == app.id
    assert len(data["documents"]) == 1
    assert data["documents"][0]["markdown_content"] == "# CV"


def test_approve_document_and_filling_gate(client, db_session, tmp_path, monkeypatch) -> None:
    """Document approval satisfies require_doc_approval before filling."""
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "true")
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session, ats_min_score=0.5)
    app, _, _ = _seed_pipeline(db_session)

    gen = client.post(f"/api/v1/applications/{app.id}/generate")
    assert gen.status_code == 200
    docs = gen.json()["documents"]

    for doc in docs:
        approve = client.patch(
            f"/api/v1/applications/{app.id}/documents/{doc['id']}/approve",
            json={"approved": True},
        )
        assert approve.status_code == 200
        assert approve.json()["approved"] is True

    fill = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "filling"},
    )
    assert fill.status_code == 200
    assert fill.json()["status"] == "filling"


def test_approve_document_blocks_without_ats_score(client, db_session) -> None:
    """Cannot approve documents that have not passed ATS critique."""
    _seed_policy(db_session)
    app, _, _ = _seed_pipeline(db_session)
    app.status = ApplicationStatus.DOCS_READY
    doc = GeneratedDocument(
        application_id=app.id,
        doc_type=DocumentType.CV,
        markdown_content="# CV",
        approved=False,
    )
    db_session.add(doc)
    db_session.commit()

    response = client.patch(
        f"/api/v1/applications/{app.id}/documents/{doc.id}/approve",
        json={"approved": True},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_generation_fails_when_critic_never_passes(db_session, tmp_path, monkeypatch) -> None:
    """Generation fails after max critic iterations."""
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    class AlwaysFailGenerator(DocumentGenerator):
        async def generate_cv(self, *, profile_context: str, job_context: str) -> str:
            return "bad"

        async def generate_cover_letter(self, *, profile_context: str, job_context: str) -> str:
            return "bad"

        async def revise_document(self, **kwargs: object) -> str:
            return "still bad"

    _seed_policy(db_session, ats_min_score=0.9)
    app, person, job = _seed_pipeline(db_session)

    with pytest.raises(DocumentGenerationError, match="ATS critic did not pass"):
        await generate_application_documents(
            db_session,
            app.id,
            person.id,
            job.id,
            generator=AlwaysFailGenerator(),
            settings=get_settings(),
        )
