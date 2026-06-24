"""Tests for application pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seejob.browser.actuator import ApplyFillResult
from seejob.browser.interfaces import BrowserActionResult
from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.job import Job, JobStatus
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig
from seejob.services.events import clear_events, list_events
from seejob.services.pipeline import PipelineAction, find_pipeline_candidates, run_pipeline_for_application
from seejob.services.rate_limit import RateLimitExceeded, check_rate_limit, record_apply_run


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": False,
        "require_doc_approval": True,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "ats_min_score": 0.7,
        "daily_apply_limit": 10,
        "rate_limits_json": '{"default": 2}',
        "blocked_companies_json": "[]",
        "blocked_keywords_json": "[]",
        "sourcing_enabled": True,
        "sourcing_schedule": "0 8 * * *",
        "sourcing_interval_minutes": 60,
    }
    defaults.update(overrides)
    policy = PolicyConfig(**defaults)
    db_session.add(policy)
    db_session.commit()
    return policy


_seed_counter = 0


def _seed_app(
    db_session,
    *,
    status: ApplicationStatus = ApplicationStatus.PENDING_APPROVAL,
    job_status: JobStatus = JobStatus.REVIEWED,
    doc_approved: bool = True,
    platform: str = "greenhouse",
) -> Application:
    global _seed_counter
    _seed_counter += 1
    person = Person(
        full_name="Applicant",
        email=f"applicant-{_seed_counter}@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    job = Job(
        url=f"https://example.com/jobs/{_seed_counter}-{status.value}",
        title="Engineer",
        company="Acme",
        source=platform,
        status=job_status,
    )
    db_session.add_all([person, job])
    db_session.flush()
    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=status,
        platform=platform,
    )
    db_session.add(app)
    db_session.flush()
    if status not in (ApplicationStatus.PENDING_APPROVAL, ApplicationStatus.DISCOVERED):
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


@pytest.mark.asyncio
async def test_pipeline_skips_pending_approval_without_auto_apply(db_session) -> None:
    _seed_policy(db_session, auto_apply=False)
    app = _seed_app(db_session, status=ApplicationStatus.PENDING_APPROVAL)

    result = await run_pipeline_for_application(db_session, app.id)

    assert result.action == PipelineAction.SKIPPED
    assert result.status == ApplicationStatus.PENDING_APPROVAL
    assert "approval" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_pipeline_generates_docs_with_auto_apply(db_session) -> None:
    _seed_policy(db_session, auto_apply=True, require_doc_approval=False)
    app = _seed_app(db_session, status=ApplicationStatus.PENDING_APPROVAL)

    with patch("seejob.services.pipeline.queue_document_generation") as mock_gen:
        mock_gen.return_value = MagicMock()
        result = await run_pipeline_for_application(db_session, app.id)

    mock_gen.assert_called_once_with(db_session, app.id)
    assert result.action in (PipelineAction.DOCS_GENERATED, PipelineAction.SKIPPED, PipelineAction.APPLIED)


@pytest.mark.asyncio
async def test_pipeline_applies_when_docs_ready(db_session) -> None:
    _seed_policy(db_session, require_doc_approval=False, require_submit_approval=False)
    app = _seed_app(db_session, status=ApplicationStatus.DOCS_READY, doc_approved=True)

    mock_actuator = MagicMock()
    mock_actuator.apply = AsyncMock(
        return_value=ApplyFillResult(
            result=BrowserActionResult.SUCCESS,
            fields_filled=3,
            message="filled",
        )
    )
    mock_actuator.close = AsyncMock()

    result = await run_pipeline_for_application(
        db_session,
        app.id,
        dry_run=True,
        actuator=mock_actuator,
    )

    assert result.action == PipelineAction.APPLIED
    mock_actuator.apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_pauses_on_needs_manual(db_session) -> None:
    _seed_policy(db_session, require_doc_approval=False)
    app = _seed_app(db_session, status=ApplicationStatus.DOCS_READY, doc_approved=True)

    mock_actuator = MagicMock()
    mock_actuator.apply = AsyncMock(
        return_value=ApplyFillResult(
            result=BrowserActionResult.CAPTCHA,
            fields_filled=0,
            message="captcha detected",
            screenshot_path="/tmp/cap.png",
            page_url="https://apply.example.com",
        )
    )
    mock_actuator.close = AsyncMock()

    clear_events()
    result = await run_pipeline_for_application(
        db_session,
        app.id,
        dry_run=True,
        actuator=mock_actuator,
    )

    db_session.refresh(app)
    assert result.action == PipelineAction.PAUSED
    assert app.status == ApplicationStatus.NEEDS_MANUAL
    assert app.interrupt_metadata_json is not None
    assert any(e["event_type"] == "needs_manual" for e in list_events())


def test_find_pipeline_candidates_respects_auto_apply(db_session) -> None:
    policy = _seed_policy(db_session, auto_apply=False)
    ready = _seed_app(db_session, status=ApplicationStatus.DOCS_READY, doc_approved=True)
    pending = _seed_app(
        db_session,
        status=ApplicationStatus.PENDING_APPROVAL,
        job_status=JobStatus.REVIEWED,
    )

    candidates = find_pipeline_candidates(db_session, policy)
    ids = {a.id for a in candidates}
    assert ready.id in ids
    assert pending.id not in ids


def test_rate_limit_blocks_after_cap(db_session) -> None:
    _seed_policy(db_session, rate_limits_json='{"greenhouse": 1}')
    record_apply_run(
        db_session,
        application_id=1,
        platform="greenhouse",
        success=True,
    )
    db_session.commit()

    with pytest.raises(RateLimitExceeded):
        check_rate_limit(db_session, "greenhouse")

    status = check_rate_limit(db_session, "linkedin")
    assert status.allowed

