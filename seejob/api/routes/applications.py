"""Application pipeline endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seejob.core.dependencies import get_session
from seejob.models.application import Application, ApplicationStatus
from seejob.schemas.application import (
    ApplicationPipelineView,
    ApplicationRead,
    ApplicationStatusUpdate,
)
from seejob.services.state_machine import InvalidTransitionError, transition

router = APIRouter()


@router.get("", response_model=list[ApplicationRead])
def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> list[Application]:
    """List applications with optional status filter."""
    stmt = (
        select(Application)
        .options(selectinload(Application.documents))
        .order_by(Application.updated_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Application.status == status_filter)
    stmt = stmt.offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/pipeline", response_model=list[ApplicationPipelineView])
def pipeline_view(db: Session = Depends(get_session)) -> list[ApplicationPipelineView]:
    """Return applications grouped by pipeline status for kanban-style views."""
    counts = dict(
        db.execute(
            select(Application.status, func.count())
            .group_by(Application.status)
        ).all()
    )

    views: list[ApplicationPipelineView] = []
    for app_status in ApplicationStatus:
        apps = list(
            db.scalars(
                select(Application)
                .where(Application.status == app_status)
                .options(selectinload(Application.documents))
                .order_by(Application.updated_at.desc())
                .limit(20)
            ).all()
        )
        views.append(
            ApplicationPipelineView(
                status=app_status,
                count=counts.get(app_status, 0),
                applications=apps,
            )
        )
    return views


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(application_id: int, db: Session = Depends(get_session)) -> Application:
    """Get a single application with documents."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return app


@router.patch("/{application_id}/status", response_model=ApplicationRead)
def update_application_status(
    application_id: int,
    data: ApplicationStatusUpdate,
    db: Session = Depends(get_session),
) -> Application:
    """Transition application to a new status via the state machine."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    try:
        app.status = transition(app.status, data.target_status)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if data.message:
        app.status_message = data.message
    db.commit()
    db.refresh(app)
    return app
