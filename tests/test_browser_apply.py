"""Tests for apply API endpoint with mocked Playwright actuator."""

from unittest.mock import AsyncMock, patch

import pytest

from seejob.browser.actuator import ApplyFillResult
from seejob.browser.interfaces import BrowserActionResult
from seejob.models.application import (
    Application,
    ApplicationStatus,
    DocumentType,
    GeneratedDocument,
)
from seejob.models.job import Job, JobStatus
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig


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


def _seed_ready_application(db_session, *, doc_approved: bool = True) -> Application:
    person = Person(
        full_name="Applicant",
        email="applicant@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    job = Job(
        url="https://careers.example.com/apply/1",
        title="Engineer",
        company="Acme",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add_all([person, job])
    db_session.flush()
    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=ApplicationStatus.DOCS_READY,
    )
    db_session.add(app)
    db_session.flush()
    db_session.add(
        GeneratedDocument(
            application_id=app.id,
            doc_type=DocumentType.CV,
            markdown_content="# CV",
            approved=doc_approved,
        )
    )
    db_session.commit()
    db_session.refresh(app)
    return app


@pytest.fixture
def mock_actuator():
    actuator = AsyncMock()
    actuator.apply = AsyncMock(
        return_value=ApplyFillResult(
            result=BrowserActionResult.SUCCESS,
            fields_filled=3,
            message="Dry run complete",
            screenshot_path="/tmp/shot.png",
            page_url="https://careers.example.com/apply/1",
        )
    )
    actuator.close = AsyncMock()
    return actuator


def test_apply_endpoint_blocks_without_doc_approval(client, db_session) -> None:
    _seed_policy(db_session)
    app = _seed_ready_application(db_session, doc_approved=False)

    response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=true")
    assert response.status_code == 409
    assert "Document approval required" in response.json()["detail"]


def test_apply_endpoint_dry_run_success(client, db_session, mock_actuator) -> None:
    _seed_policy(db_session)
    app = _seed_ready_application(db_session, doc_approved=True)

    with patch("seejob.services.apply.PlaywrightActuator", return_value=mock_actuator):
        response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=true")

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "success"
    assert data["fields_filled"] == 3
    assert data["dry_run"] is True
    assert data["submitted"] is False
    assert data["status"] == "filling"
    mock_actuator.apply.assert_awaited_once()
    mock_actuator.close.assert_awaited_once()


def test_apply_endpoint_auth_required_interrupt(client, db_session, mock_actuator) -> None:
    _seed_policy(db_session)
    app = _seed_ready_application(db_session)
    mock_actuator.apply.return_value = ApplyFillResult(
        result=BrowserActionResult.AUTH_REQUIRED,
        message="Login required",
        page_url="https://careers.example.com/login",
    )

    with patch("seejob.services.apply.PlaywrightActuator", return_value=mock_actuator):
        response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=true")

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "auth_required"
    assert data["status"] == "auth_required"


def test_apply_endpoint_captcha_transitions_needs_manual(client, db_session, mock_actuator) -> None:
    _seed_policy(db_session)
    app = _seed_ready_application(db_session)
    mock_actuator.apply.return_value = ApplyFillResult(
        result=BrowserActionResult.CAPTCHA,
        message="CAPTCHA detected",
        page_url="https://careers.example.com/apply/1",
    )

    with patch("seejob.services.apply.PlaywrightActuator", return_value=mock_actuator):
        response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=true")

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == "captcha"
    assert data["status"] == "needs_manual"
    assert "careers.example.com" in data["page_url"]


def test_apply_without_submit_approval_fills_only(client, db_session, mock_actuator) -> None:
    """Non-dry-run without submit_approved fills form but does not submit."""
    _seed_policy(db_session)
    app = _seed_ready_application(db_session)
    app.status = ApplicationStatus.FILLING
    db_session.commit()

    with patch("seejob.services.apply.PlaywrightActuator", return_value=mock_actuator):
        response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=false")

    assert response.status_code == 200
    data = response.json()
    assert data["submitted"] is False
    assert data["status"] == "filling"
    mock_actuator.apply.assert_awaited_once()
    call_kwargs = mock_actuator.apply.await_args.kwargs
    assert call_kwargs["dry_run"] is False
    assert call_kwargs["submit"] is False


def test_apply_endpoint_blocks_when_rate_limited(client, db_session, mock_actuator) -> None:
    """POST /apply enforces daily apply caps before browser automation."""
    _seed_policy(db_session, rate_limits_json='{"greenhouse": 1}')
    from seejob.services.rate_limit import record_apply_run

    record_apply_run(
        db_session,
        application_id=999,
        platform="greenhouse",
        success=True,
    )
    db_session.commit()

    app = _seed_ready_application(db_session, doc_approved=True)
    app.platform = "greenhouse"
    db_session.commit()

    with patch("seejob.services.apply.PlaywrightActuator", return_value=mock_actuator):
        response = client.post(f"/api/v1/applications/{app.id}/apply?dry_run=false")

    assert response.status_code == 429
    mock_actuator.apply.assert_not_awaited()
