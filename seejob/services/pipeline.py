"""Application pipeline orchestrator — ties document generation and browser apply."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from seejob.browser.interfaces import BrowserActionResult
from seejob.models.application import Application, ApplicationStatus
from seejob.models.job import Job, JobStatus
from seejob.models.policy import PolicyConfig
from seejob.services.apply import ApplyError, is_awaiting_submit_approval, run_application_apply
from seejob.services.documents import DocumentGenerationError, queue_document_generation
from seejob.services.events import emit_event
from seejob.services.interrupts import load_interrupt_metadata
from seejob.services.policy import get_policy_config
from seejob.services.rate_limit import RateLimitExceeded
from seejob.services.state_machine import InvalidTransitionError, transition

logger = logging.getLogger(__name__)

PIPELINE_CLAIM_LEASE_SECONDS = 900


class PipelineAction(StrEnum):
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


def _claim_expired_before(
    now: datetime | None = None,
    *,
    lease_seconds: int = PIPELINE_CLAIM_LEASE_SECONDS,
) -> str:
    current = now or datetime.now(UTC)
    return (current - timedelta(seconds=lease_seconds)).isoformat()


def has_active_pipeline_claim(
    app: Application,
    now: datetime | None = None,
    *,
    lease_seconds: int = PIPELINE_CLAIM_LEASE_SECONDS,
) -> bool:
    """Return True when another tick holds a non-expired pipeline lease."""
    if not app.pipeline_claimed_at:
        return False
    return app.pipeline_claimed_at >= _claim_expired_before(now, lease_seconds=lease_seconds)


def try_claim_pipeline_application(
    db: Session,
    application_id: int,
    *,
    lease_seconds: int = PIPELINE_CLAIM_LEASE_SECONDS,
) -> bool:
    """Claim an application row for the current pipeline tick."""
    now_iso = datetime.now(UTC).isoformat()
    expiry = _claim_expired_before(lease_seconds=lease_seconds)
    result = db.execute(
        update(Application)
        .where(
            Application.id == application_id,
            or_(
                Application.pipeline_claimed_at.is_(None),
                Application.pipeline_claimed_at < expiry,
            ),
        )
        .values(pipeline_claimed_at=now_iso)
    )
    db.flush()
    return (result.rowcount or 0) > 0


def release_pipeline_claim(db: Session, application_id: int) -> None:
    """Release a pipeline lease after processing completes."""
    db.execute(
        update(Application)
        .where(Application.id == application_id)
        .values(pipeline_claimed_at=None)
    )
    db.flush()


def _is_eligible_pipeline_candidate(app: Application, policy: PolicyConfig) -> bool:
    if is_awaiting_submit_approval(app, policy):
        return False
    if has_active_pipeline_claim(app):
        return False
    if app.status == ApplicationStatus.FILLING and app.interrupt_metadata_json:
        return False
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
    if not try_claim_pipeline_application(db, application_id):
        exists = db.scalar(select(Application.id).where(Application.id == application_id))
        if exists is None:
            return PipelineResult(
                application_id=application_id,
                status=ApplicationStatus.FAILED,
                action=PipelineAction.FAILED,
                message=f"Application {application_id} not found",
            )
        return PipelineResult(
            application_id=application_id,
            status=ApplicationStatus.FILLING,
            action=PipelineAction.SKIPPED,
            message="Application is locked by another pipeline run",
        )

    try:
        return await _run_pipeline_for_application_locked(
            db,
            application_id,
            dry_run=dry_run,
            submit_approved=submit_approved,
            actuator=actuator,
        )
    finally:
        release_pipeline_claim(db, application_id)
        db.commit()


async def _run_pipeline_for_application_locked(
    db: Session,
    application_id: int,
    *,
    dry_run: bool = False,
    submit_approved: bool | None = None,
    actuator: object | None = None,
) -> PipelineResult:
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
        if is_awaiting_submit_approval(app, policy):
            return PipelineResult(
                application_id=app.id,
                status=app.status,
                action=PipelineAction.SKIPPED,
                message="Awaiting submit approval",
            )

        platform = _resolve_platform(app)
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
    eligible = [app for app in apps if _is_eligible_pipeline_candidate(app, policy)]
    if policy.auto_apply:
        return eligible

    return [app for app in eligible if _can_auto_progress_docs(app, policy)]
