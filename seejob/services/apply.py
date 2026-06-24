"""Application form-fill orchestration via BrowserActuator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seejob.browser.actuator import PlaywrightActuator
from seejob.browser.interfaces import BrowserActionResult
from seejob.models.application import Application, ApplicationStatus
from seejob.models.policy import PolicyConfig
from seejob.services.approval import ApprovalGateError, validate_approval_gates
from seejob.services.interrupts import set_interrupt
from seejob.services.policy import get_policy_config
from seejob.services.state_machine import InvalidTransitionError, transition

logger = logging.getLogger(__name__)


class ApplyError(ValueError):
    """Raised when apply cannot proceed."""


@dataclass
class ApplyResult:
    """Outcome of an apply orchestration run."""

    application_id: int
    status: ApplicationStatus
    result: BrowserActionResult
    fields_filled: int
    message: str | None
    screenshot_path: str | None
    page_url: str | None
    dry_run: bool
    submitted: bool = False


async def run_application_apply(
    db: Session,
    application_id: int,
    *,
    dry_run: bool = True,
    submit_approved: bool = False,
    actuator: object | None = None,
) -> ApplyResult:
    """Validate gates, transition state, and run browser apply."""
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
        raise ApplyError(f"Application {application_id} not found")

    policy = get_policy_config(db)
    _validate_apply_gates(app, policy, dry_run=dry_run, submit_approved=submit_approved)

    if app.status != ApplicationStatus.FILLING:
        try:
            app.status = transition(app.status, ApplicationStatus.FILLING)
            db.commit()
        except InvalidTransitionError as exc:
            raise ApplyError(str(exc)) from exc

    browser = actuator or PlaywrightActuator()
    try:
        fill_result = await browser.apply(
            application_id,
            db,
            dry_run=dry_run,
            submit=not dry_run and submit_approved,
        )
    finally:
        await browser.close()

    if fill_result.result in (BrowserActionResult.CAPTCHA, BrowserActionResult.NEEDS_MANUAL):
        set_interrupt(
            app,
            ApplicationStatus.NEEDS_MANUAL,
            {
                "reason": fill_result.result.value,
                "screenshot_path": fill_result.screenshot_path,
                "page_url": fill_result.page_url,
            },
            message=fill_result.message,
        )
        db.commit()
        return ApplyResult(
            application_id=application_id,
            status=app.status,
            result=fill_result.result,
            fields_filled=fill_result.fields_filled,
            message=fill_result.message,
            screenshot_path=fill_result.screenshot_path,
            page_url=fill_result.page_url,
            dry_run=dry_run,
        )

    if fill_result.result == BrowserActionResult.AUTH_REQUIRED:
        set_interrupt(
            app,
            ApplicationStatus.AUTH_REQUIRED,
            {
                "reason": "auth_required",
                "screenshot_path": fill_result.screenshot_path,
                "page_url": fill_result.page_url,
            },
            message=fill_result.message,
        )
        db.commit()
        return ApplyResult(
            application_id=application_id,
            status=app.status,
            result=fill_result.result,
            fields_filled=fill_result.fields_filled,
            message=fill_result.message,
            screenshot_path=fill_result.screenshot_path,
            page_url=fill_result.page_url,
            dry_run=dry_run,
        )

    if fill_result.result == BrowserActionResult.FAILED:
        app.status_message = fill_result.message
        db.commit()
        return ApplyResult(
            application_id=application_id,
            status=app.status,
            result=fill_result.result,
            fields_filled=fill_result.fields_filled,
            message=fill_result.message,
            screenshot_path=fill_result.screenshot_path,
            page_url=fill_result.page_url,
            dry_run=dry_run,
        )

    submitted = False
    if not dry_run and submit_approved and fill_result.result == BrowserActionResult.SUCCESS:
        try:
            validate_approval_gates(
                app,
                policy,
                ApplicationStatus.SUBMITTED,
                submit_approved=True,
            )
            app.status = transition(app.status, ApplicationStatus.SUBMITTED)
            app.submitted_at = datetime.now(UTC).isoformat()
            app.status_message = "Application submitted"
            submitted = True
        except (ApprovalGateError, InvalidTransitionError) as exc:
            app.status_message = str(exc)
    elif not dry_run:
        if policy.require_submit_approval:
            app.status_message = "Form filled; awaiting submit approval"
        else:
            app.status_message = fill_result.message
    else:
        app.status_message = fill_result.message or "Dry run complete"

    db.commit()
    db.refresh(app)

    return ApplyResult(
        application_id=application_id,
        status=app.status,
        result=fill_result.result,
        fields_filled=fill_result.fields_filled,
        message=app.status_message,
        screenshot_path=fill_result.screenshot_path,
        page_url=fill_result.page_url,
        dry_run=dry_run,
        submitted=submitted,
    )


def _validate_apply_gates(
    app: Application,
    policy: PolicyConfig,
    *,
    dry_run: bool,
    submit_approved: bool,
) -> None:
    """Enforce document approval before any apply attempt."""
    if policy.auto_apply:
        return

    if policy.require_doc_approval:
        if not app.documents or not all(doc.approved for doc in app.documents):
            raise ApprovalGateError(
                "Document approval required before applying. "
                "Approve all generated documents or disable require_doc_approval."
            )

    if not dry_run and submit_approved and policy.require_submit_approval:
        validate_approval_gates(
            app,
            policy,
            ApplicationStatus.SUBMITTED,
            submit_approved=True,
        )
