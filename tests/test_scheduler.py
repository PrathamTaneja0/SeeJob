"""Tests for scheduled worker tick (sourcing + pipeline queue)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seejob.models.application import (
    Application,
    ApplicationStatus,
    DocumentType,
    GeneratedDocument,
)
from seejob.models.job import Job, JobStatus
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig
from seejob.services.events import clear_events, list_events
from seejob.services.pipeline import PipelineAction, PipelineResult
from seejob.services.sourcing.pipeline import SourcingRunResult
from seejob.workers.base import WorkerStatus
from seejob.workers.scheduler import (
    process_approved_pipeline_queue,
    run_scheduled_tick,
    run_scheduler_worker,
)


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": True,
        "require_doc_approval": False,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "ats_min_score": 0.7,
        "daily_apply_limit": 10,
        "rate_limits_json": '{"default": 10}',
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


def _seed_docs_ready_app(db_session) -> Application:
    person = Person(
        full_name="Applicant",
        email="scheduler@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    job = Job(
        url="https://example.com/jobs/1",
        title="Engineer",
        company="Acme",
        source="greenhouse",
        status=JobStatus.REVIEWED,
    )
    db_session.add_all([person, job])
    db_session.flush()
    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=ApplicationStatus.DOCS_READY,
        platform="greenhouse",
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


@pytest.mark.asyncio
async def test_run_scheduled_tick_skips_sourcing_when_disabled(db_session) -> None:
    _seed_policy(db_session, sourcing_enabled=False)
    clear_events()

    with patch(
        "seejob.workers.scheduler.run_sourcing_tick",
        new_callable=AsyncMock,
    ) as mock_sourcing:
        result = await run_scheduled_tick(db_session, skip_sourcing=False)

    mock_sourcing.assert_not_called()
    assert "sourcing skipped" in result.sourcing_message
    assert any(e["event_type"] == "scheduler_tick" for e in list_events())


@pytest.mark.asyncio
async def test_run_scheduled_tick_runs_sourcing_then_pipeline(db_session) -> None:
    _seed_policy(db_session)
    _seed_docs_ready_app(db_session)
    clear_events()

    sourcing_result = SourcingRunResult(fetched=1, created=0, scored=0)
    pipeline_result = PipelineResult(
        application_id=1,
        status=ApplicationStatus.FILLING,
        action=PipelineAction.APPLIED,
        message="filled",
    )

    with (
        patch(
            "seejob.workers.scheduler.run_sourcing_tick",
            new_callable=AsyncMock,
            return_value=sourcing_result,
        ) as mock_sourcing,
        patch(
            "seejob.workers.scheduler.run_pipeline_for_application",
            new_callable=AsyncMock,
            return_value=pipeline_result,
        ) as mock_pipeline,
    ):
        result = await run_scheduled_tick(db_session)

    mock_sourcing.assert_awaited_once()
    mock_pipeline.assert_awaited()
    assert result.pipeline_processed == 1
    assert result.pipeline_submitted == 0
    assert any(e["event_type"] == "scheduler_complete" for e in list_events())


@pytest.mark.asyncio
async def test_process_approved_pipeline_queue_counts_outcomes(db_session) -> None:
    _seed_policy(db_session)
    app = _seed_docs_ready_app(db_session)

    with patch(
        "seejob.workers.scheduler.run_pipeline_for_application",
        new_callable=AsyncMock,
        return_value=PipelineResult(
            application_id=app.id,
            status=ApplicationStatus.SUBMITTED,
            action=PipelineAction.SUBMITTED,
        ),
    ):
        result = await process_approved_pipeline_queue(db_session)

    assert result.pipeline_processed == 1
    assert result.pipeline_submitted == 1
    assert result.pipeline_skipped == 0


@pytest.mark.asyncio
async def test_run_scheduler_worker_returns_worker_result(db_session) -> None:
    _seed_policy(db_session, sourcing_enabled=False)

    with patch(
        "seejob.workers.scheduler.run_scheduled_tick",
        new_callable=AsyncMock,
        return_value=MagicMock(
            sourcing_message="sourcing skipped",
            pipeline_processed=0,
            pipeline_submitted=0,
            pipeline_paused=0,
            pipeline_skipped=0,
            pipeline_failed=0,
            errors=[],
            summary="sourcing skipped; pipeline processed=0",
        ),
    ):
        result = await run_scheduler_worker(db_session, skip_sourcing=True)

    assert result.worker_name == "scheduler"
    assert result.status == WorkerStatus.COMPLETED
