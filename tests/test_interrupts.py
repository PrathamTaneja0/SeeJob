"""Tests for interrupt handling and resume API."""

from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.job import Job, JobStatus
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig
from seejob.services.interrupts import load_interrupt_metadata, resume_from_interrupt, set_interrupt


def _seed(db_session) -> Application:
    policy = PolicyConfig(
        id=1,
        auto_apply=False,
        require_doc_approval=True,
        require_submit_approval=True,
        min_fit_score=0.6,
        ats_min_score=0.7,
        daily_apply_limit=10,
        rate_limits_json='{"default": 10}',
        blocked_companies_json="[]",
        blocked_keywords_json="[]",
        sourcing_enabled=True,
        sourcing_schedule="0 8 * * *",
        sourcing_interval_minutes=60,
    )
    person = Person(
        full_name="Applicant",
        email="a@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    job = Job(
        url="https://example.com/jobs/manual",
        title="Engineer",
        company="Acme",
        source="test",
        status=JobStatus.REVIEWED,
    )
    db_session.add_all([policy, person, job])
    db_session.flush()
    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=ApplicationStatus.FILLING,
    )
    db_session.add(app)
    db_session.flush()
    db_session.add(
        GeneratedDocument(
            application_id=app.id,
            doc_type=DocumentType.CV,
            markdown_content="# CV",
            approved=True,
        )
    )
    db_session.commit()
    db_session.refresh(app)
    return app


def test_set_interrupt_stores_metadata(db_session) -> None:
    app = _seed(db_session)
    set_interrupt(
        app,
        ApplicationStatus.NEEDS_MANUAL,
        {"reason": "captcha", "page_url": "https://x.com"},
        message="Solve captcha",
    )
    db_session.commit()
    meta = load_interrupt_metadata(app)
    assert meta["reason"] == "captcha"
    assert app.status == ApplicationStatus.NEEDS_MANUAL


def test_resume_from_interrupt_clears_metadata(db_session) -> None:
    app = _seed(db_session)
    set_interrupt(app, ApplicationStatus.NEEDS_MANUAL, {"reason": "captcha"})
    db_session.commit()

    resumed = resume_from_interrupt(db_session, app, note="done")
    assert resumed.status == ApplicationStatus.FILLING
    assert resumed.interrupt_metadata_json is None


def test_resume_api_endpoint(client, db_session) -> None:
    app = _seed(db_session)
    set_interrupt(app, ApplicationStatus.NEEDS_MANUAL, {"reason": "captcha"})
    db_session.commit()

    response = client.post(
        f"/api/v1/applications/{app.id}/resume",
        json={"note": "captcha solved"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "filling"
    assert data["interrupt_metadata_json"] is None


def test_resume_rejects_wrong_status(client, db_session) -> None:
    app = _seed(db_session)
    app.status = ApplicationStatus.DOCS_READY
    db_session.commit()

    response = client.post(f"/api/v1/applications/{app.id}/resume")
    assert response.status_code == 409
