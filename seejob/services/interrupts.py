"""Interrupt handling for needs_manual and auth_required pipeline pauses."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from seejob.models.application import Application, ApplicationStatus
from seejob.services.state_machine import InvalidTransitionError, transition


class InterruptError(ValueError):
    """Raised when interrupt operations are invalid."""


def load_interrupt_metadata(app: Application) -> dict[str, Any]:
    """Parse interrupt metadata JSON from an application."""
    if not app.interrupt_metadata_json:
        return {}
    try:
        data = json.loads(app.interrupt_metadata_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def set_interrupt(
    app: Application,
    target_status: ApplicationStatus,
    metadata: dict[str, Any],
    *,
    message: str | None = None,
) -> None:
    """Transition to an interrupt state and store metadata."""
    if target_status not in (ApplicationStatus.NEEDS_MANUAL, ApplicationStatus.AUTH_REQUIRED):
        raise InterruptError(f"Not an interrupt status: {target_status.value}")

    app.status = transition(app.status, target_status)
    payload = dict(metadata)
    if message:
        payload.setdefault("message", message)
        app.status_message = message
    app.interrupt_metadata_json = json.dumps(payload)


def clear_interrupt(app: Application) -> None:
    """Remove interrupt metadata after manual resolution."""
    app.interrupt_metadata_json = None


def resume_from_interrupt(
    db: Session,
    application: Application,
    *,
    note: str | None = None,
) -> Application:
    """Resume filling after manual captcha solve or auth completion."""
    if application.status not in (
        ApplicationStatus.NEEDS_MANUAL,
        ApplicationStatus.AUTH_REQUIRED,
    ):
        raise InterruptError(
            f"Application must be needs_manual or auth_required "
            f"(current: {application.status.value})"
        )

    try:
        application.status = transition(application.status, ApplicationStatus.FILLING)
    except InvalidTransitionError as exc:
        raise InterruptError(str(exc)) from exc

    clear_interrupt(application)
    application.status_message = note or "Resumed after manual intervention"
    db.commit()
    db.refresh(application)
    return application
