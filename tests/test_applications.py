"""Tests for application status API and approval gates."""

from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.job import Job, JobStatus
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig


def _seed_person_job(db_session) -> tuple[Person, Job]:
    person = Person(
        full_name="Applicant",
        email="applicant@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    job = Job(
        url="https://example.com/jobs/1",
        title="Engineer",
        company="Acme",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add_all([person, job])
    db_session.commit()
    return person, job


def _seed_application(
    db_session,
    *,
    status: ApplicationStatus = ApplicationStatus.DOCS_READY,
    doc_approved: bool = False,
) -> Application:
    person, job = _seed_person_job(db_session)
    app = Application(person_id=person.id, job_id=job.id, status=status)
    db_session.add(app)
    db_session.flush()
    doc = GeneratedDocument(
        application_id=app.id,
        doc_type=DocumentType.CV,
        markdown_content="# CV",
        approved=doc_approved,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(app)
    return app


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": False,
        "require_doc_approval": True,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "ats_min_score": 0.7,
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


def test_doc_approval_gate_blocks_filling(client, db_session) -> None:
    """Transition to filling is blocked when documents are not approved."""
    _seed_policy(db_session)
    app = _seed_application(db_session, doc_approved=False)

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "filling"},
    )
    assert response.status_code == 409
    assert "Document approval required" in response.json()["detail"]


def test_doc_approval_gate_allows_filling_when_approved(client, db_session) -> None:
    """Approved documents satisfy the doc approval gate."""
    _seed_policy(db_session)
    app = _seed_application(db_session, doc_approved=True)

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "filling"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "filling"


def test_submit_approval_gate_blocks_submitted(client, db_session) -> None:
    """Transition to submitted requires explicit submit_approved."""
    _seed_policy(db_session)
    app = _seed_application(db_session, status=ApplicationStatus.FILLING, doc_approved=True)

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "submitted"},
    )
    assert response.status_code == 409
    assert "Submit approval required" in response.json()["detail"]


def test_submit_approval_gate_allows_submitted(client, db_session) -> None:
    """Submit transition succeeds when submit_approved is set."""
    _seed_policy(db_session)
    app = _seed_application(db_session, status=ApplicationStatus.FILLING, doc_approved=True)

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "submitted", "submit_approved": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "submitted"
    assert data["submitted_at"] is not None


def test_auto_apply_skips_approval_gates(client, db_session) -> None:
    """auto_apply bypasses doc and submit approval gates."""
    _seed_policy(db_session, auto_apply=True)
    app = _seed_application(db_session, status=ApplicationStatus.FILLING, doc_approved=False)

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "submitted"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


def test_duplicate_application_constraint(db_session) -> None:
    """Database rejects duplicate person/job application pairs."""
    from sqlalchemy.exc import IntegrityError

    person, job = _seed_person_job(db_session)
    db_session.add(Application(person_id=person.id, job_id=job.id))
    db_session.commit()

    db_session.add(Application(person_id=person.id, job_id=job.id))
    try:
        db_session.commit()
        raise AssertionError("Expected IntegrityError for duplicate application")
    except IntegrityError:
        db_session.rollback()


def test_resume_endpoint_clears_interrupt(client, db_session) -> None:
    """POST /resume transitions needs_manual back to filling."""
    _seed_policy(db_session)
    app = _seed_application(db_session, status=ApplicationStatus.NEEDS_MANUAL, doc_approved=True)
    app.interrupt_metadata_json = '{"reason": "captcha"}'
    app.status_message = "Captcha detected"
    db_session.commit()

    response = client.post(
        f"/api/v1/applications/{app.id}/resume",
        json={"note": "Captcha solved manually"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "filling"
    assert data["interrupt_metadata_json"] is None
    assert "Captcha solved" in (data["status_message"] or "")


def test_resume_endpoint_rejects_wrong_status(client, db_session) -> None:
    """Resume is only valid from interrupt states."""
    _seed_policy(db_session)
    app = _seed_application(db_session, status=ApplicationStatus.DOCS_READY, doc_approved=True)

    response = client.post(f"/api/v1/applications/{app.id}/resume")
    assert response.status_code == 409


def test_patch_status_clears_interrupt_when_leaving_needs_manual(client, db_session) -> None:
    """PATCH away from interrupt states clears interrupt metadata."""
    _seed_policy(db_session)
    app = _seed_application(db_session, status=ApplicationStatus.NEEDS_MANUAL, doc_approved=True)
    app.interrupt_metadata_json = '{"reason": "captcha"}'
    db_session.commit()

    response = client.patch(
        f"/api/v1/applications/{app.id}/status",
        json={"target_status": "failed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["interrupt_metadata_json"] is None


def test_download_document_pdf(client, db_session, tmp_path) -> None:
    """GET /documents/{doc_id}/download serves the generated PDF file."""
    _seed_policy(db_session)
    app = _seed_application(db_session, doc_approved=False)
    pdf_path = tmp_path / "cv.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    doc = db_session.query(GeneratedDocument).filter_by(application_id=app.id).one()
    doc.pdf_path = str(pdf_path)
    db_session.commit()

    response = client.get(f"/api/v1/applications/{app.id}/documents/{doc.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF")


def test_download_document_regenerates_missing_pdf(client, db_session, tmp_path, monkeypatch) -> None:
    """Missing PDF on disk is regenerated from stored markdown."""
    monkeypatch.setenv("SEEJOB_DOCUMENTS_DIR", str(tmp_path / "docs"))
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    _seed_policy(db_session)
    app = _seed_application(db_session, doc_approved=False)
    doc = db_session.query(GeneratedDocument).filter_by(application_id=app.id).one()
    doc.pdf_path = str(tmp_path / "missing.pdf")
    doc.markdown_content = "# Alex Rivera\n\n## Experience\n\n- Engineer at Acme Corp"
    db_session.commit()

    response = client.get(f"/api/v1/applications/{app.id}/documents/{doc.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_download_document_markdown(client, db_session) -> None:
    """GET download?format=md returns markdown attachment."""
    _seed_policy(db_session)
    app = _seed_application(db_session, doc_approved=False)
    doc = db_session.query(GeneratedDocument).filter_by(application_id=app.id).one()
    doc.markdown_content = "# Alex Rivera\n\n## Skills\n\n- Python"
    db_session.commit()

    response = client.get(
        f"/api/v1/applications/{app.id}/documents/{doc.id}/download?format=md"
    )
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "Alex Rivera" in response.text

