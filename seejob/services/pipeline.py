"""Application pipeline orchestrator — ties document generation and browser apply."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seejob.browser.interfaces import BrowserActionResult
from seejob.browser.interfaces import BrowserActionResult
from seejob.models.application import Application, ApplicationStatus
from seejob.models.job import Job, JobStatus
from seejob.models.policy import PolicyConfig
from seejob.services.apply import ApplyError, run_application_apply
from seejob.services.documents import DocumentGenerationError, queue_document_generation
from seejob.services.events import emit_event
from seejob.services.interrupts import load_interrupt_metadata
from seejob.services.policy import get_policy_config
from seejob.services.rate_limit import RateLimitExceeded, check_rate_limit, record_apply_run
from seejob.services.state_machine import InvalidTransitionError, transition

logger = logging.getLogger(__name__)


class PipelineAction(str, Enum):
    """Outcome category for a pipeline step."""

    SKIPPED = "skipped"
    DOCS_GENERATED = "docs_generated"
    APPLIED = "applied"
    SUBMITTED = "submitted"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class PipelineResult:
    """Result of running the pipeline for one application."""

    application_id: int
    status: ApplicationStatus
    action: PipelineAction
    message: str | None = None


def _resolve_platform(app: Application) -> str:
    if app.platform:
        return app.platform.lower()
    if app.job and app.job.source:
        return app.job.source.lower()
    return "default"


def _docs_approved(app: Application) -> bool:
    return bool(app.documents) and all(doc.approved for doc in app.documents)


def _can_auto_progress_docs(app: Application, policy: PolicyConfig) -> bool:
    if not app.documents:
        return False
    if policy.require_doc_approval:
        return _docs_approved(app)
    return True


async def run_pipeline_for_application(
    db: Session,
    application_id: int,
    *,
    dry_run: bool = False,
    submit_approved: bool | None = None,
    actuator: object | None = None,
) -> PipelineResult:
    """Drive one application through doc generation and apply stages."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(
            selectinload(Application.documents),
            selectinload(Application.job),
            selectinload(Application.person),
        )
    )
    if app is None:
        return PipelineResult(
            application_id=application_id,
            status=ApplicationStatus.FAILED,
            action=PipelineAction.FAILED,
            message=f"Application {application_id} not found",
        )

    policy = get_policy_config(db)
    if submit_approved is None:
        submit_approved = policy.auto_apply and not policy.require_submit_approval

    if app.status in (ApplicationStatus.NEEDS_MANUAL, ApplicationStatus.AUTH_REQUIRED):
        meta = load_interrupt_metadata(app)
        emit_event(
            "pipeline_paused",
            app.status_message or "Awaiting manual intervention",
            application_id=app.id,
            worker_name="pipeline",
            metadata=meta,
        )
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.PAUSED,
            message=app.status_message,
        )

    if app.status == ApplicationStatus.SUBMITTED:
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.SKIPPED,
            message="Already submitted",
        )

    if app.status == ApplicationStatus.PENDING_APPROVAL:
        if not policy.auto_apply:
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.SKIPPED,
                message="Awaiting human approval",
            )
        try:
            app.status = transition(app.status, ApplicationStatus.GENERATING_DOCS)
            db.commit()
        except InvalidTransitionError as exc:
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.FAILED,
                message=str(exc),
            )

    if app.status in (ApplicationStatus.PENDING_APPROVAL, ApplicationStatus.GENERATING_DOCS):
        try:
            queue_document_generation(db, application_id)
            db.refresh(app)
            emit_event(
                "docs_ready",
                "Documents generated",
                application_id=app.id,
                worker_name="pipeline",
            )
        except DocumentGenerationError as exc:
            emit_event(
                "pipeline_failed",
                str(exc),
                application_id=app.id,
                worker_name="pipeline",
            )
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.FAILED,
                message=str(exc),
            )

    if app.status == ApplicationStatus.DOCS_READY:
        if not _can_auto_progress_docs(app, policy):
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.SKIPPED,
                message="Documents require approval before apply",
            )

        platform = _resolve_platform(app)
        try:
            check_rate_limit(db, platform)
        except RateLimitExceeded as exc:
            emit_event(
                "rate_limited",
                str(exc),
                application_id=app.id,
                worker_name="pipeline",
                metadata={"platform": platform},
            )
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.SKIPPED,
                message=str(exc),
            )

        return await _run_apply_step(
            db,
            app,
            policy,
            platform=platform,
            dry_run=dry_run,
            submit_approved=submit_approved,
            actuator=actuator,
        )

    if app.status == ApplicationStatus.FILLING:
        platform = _resolve_platform(app)
        try:
            check_rate_limit(db, platform)
        except RateLimitExceeded as exc:
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.SKIPPED,
                message=str(exc),
            )
        return await _run_apply_step(
            db,
            app,
            policy,
            platform=platform,
            dry_run=dry_run,
            submit_approved=submit_approved,
            actuator=actuator,
        )

    return PipelineResult(
        application_id=app.id,
        status=app.status,
        action=PipelineAction.SKIPPED,
        message=f"No automated action for status '{app.status.value}'",
    )


async def _run_apply_step(
    db: Session,
    app: Application,
    policy: PolicyConfig,
    *,
    platform: str,
    dry_run: bool,
    submit_approved: bool,
    actuator: object | None,
) -> PipelineResult:
    """Execute browser apply and handle interrupts."""
    try:
        apply_result = await run_application_apply(
            db,
            app.id,
            dry_run=dry_run,
            submit_approved=submit_approved,
            actuator=actuator,
        )
    except ApplyError as exc:
        emit_event(
            "pipeline_failed",
            str(exc),
            application_id=app.id,
            worker_name="pipeline",
        )
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.FAILED,
            message=str(exc),
        )

    db.refresh(app)

    if app.status == ApplicationStatus.NEEDS_MANUAL:
        emit_event(
            "needs_manual",
            apply_result.message or "Manual intervention required",
            application_id=app.id,
            worker_name="pipeline",
        )
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.PAUSED,
            message=apply_result.message,
        )

    if app.status == ApplicationStatus.AUTH_REQUIRED:
        emit_event(
            "auth_required",
            apply_result.message or "Authentication required",
            application_id=app.id,
            worker_name="pipeline",
        )
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.PAUSED,
            message=apply_result.message,
        )

    if apply_result.submitted:
        record_apply_run(
            db,
            application_id=app.id,
            platform=platform,
            success=True,
            message="submitted",
        )
        db.commit()
        emit_event(
            "submitted",
            "Application submitted",
            application_id=app.id,
            worker_name="pipeline",
        )
        return PipelineResult(
            application_id=app.id,
            status=app.status,
            action=PipelineAction.SUBMITTED,
            message=apply_result.message,
        )

    if apply_result.result == BrowserActionResult.SUCCESS and not dry_run:
        record_apply_run(
            db,
            application_id=app.id,
            platform=platform,
            success=True,
            message=apply_result.message,
        )
        db.commit()

    action = PipelineAction.APPLIED
    if apply_result.result != BrowserActionResult.SUCCESS:
        action = PipelineAction.FAILED

    emit_event(
        "apply_complete",
        apply_result.message or apply_result.result.value,
        application_id=app.id,
        worker_name="pipeline",
        metadata={"dry_run": dry_run, "result": apply_result.result.value},
    )
    return PipelineResult(
        application_id=app.id,
        status=app.status,
        action=action,
        message=apply_result.message,
    )


def find_pipeline_candidates(db: Session, policy: PolicyConfig) -> list[Application]:
    """Applications eligible for automated pipeline progression on a scheduler tick."""
    stmt = (
        select(Application)
        .join(Job, Application.job_id == Job.id)
        .where(Job.status == JobStatus.REVIEWED)
        .options(selectinload(Application.documents), selectinload(Application.job))
        .order_by(Application.updated_at.asc())
    )

    if policy.auto_apply:
        stmt = stmt.where(
            Application.status.in_(
                [
                    ApplicationStatus.PENDING_APPROVAL,
                    ApplicationStatus.GENERATING_DOCS,
                    ApplicationStatus.DOCS_READY,
                    ApplicationStatus.FILLING,
                ]
            )
        )
    else:
        stmt = stmt.where(Application.status == ApplicationStatus.DOCS_READY)

    apps = list(db.scalars(stmt).all())
    if policy.auto_apply:
        return apps

    return [app for app in apps if _can_auto_progress_docs(app, policy)]
