"""Application pipeline endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seejob.core.dependencies import get_session
from seejob.models.application import Application, ApplicationStatus, GeneratedDocument
from seejob.schemas.application import (
    ApplicationApplyResponse,
    ApplicationDocumentsView,
    ApplicationPipelineView,
    ApplicationRead,
    ApplicationStatusUpdate,
    DocumentApproveUpdate,
    DocumentGenerationResponse,
    GeneratedDocumentRead,
)
from seejob.services.apply import ApplyError, run_application_apply
from seejob.services.approval import ApprovalGateError, validate_approval_gates
from seejob.services.documents import DocumentGenerationError, queue_document_generation
from seejob.services.policy import get_policy_config
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
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    policy = get_policy_config(db)

    try:
        validate_approval_gates(
            app,
            policy,
            data.target_status,
            submit_approved=data.submit_approved,
        )
    except ApprovalGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        app.status = transition(app.status, data.target_status)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if data.target_status == ApplicationStatus.SUBMITTED:
        app.submitted_at = datetime.now(UTC).isoformat()

    if data.message:
        app.status_message = data.message
    db.commit()
    db.refresh(app)
    return app


@router.post("/{application_id}/generate", response_model=DocumentGenerationResponse)
def generate_documents(application_id: int, db: Session = Depends(get_session)) -> DocumentGenerationResponse:
    """Trigger tailored document generation and transition to docs_ready."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    try:
        result = queue_document_generation(db, application_id)
    except DocumentGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.refresh(app)
    return DocumentGenerationResponse(
        application_id=application_id,
        status=app.status,
        documents=result.documents,
        message=app.status_message,
    )


@router.get("/{application_id}/documents", response_model=ApplicationDocumentsView)
def get_application_documents(
    application_id: int, db: Session = Depends(get_session)
) -> ApplicationDocumentsView:
    """Preview generated markdown and ATS critic reports."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    return ApplicationDocumentsView(
        application_id=app.id,
        status=app.status,
        documents=app.documents,
    )


@router.patch(
    "/{application_id}/documents/{doc_id}/approve",
    response_model=GeneratedDocumentRead,
)
def approve_document(
    application_id: int,
    doc_id: int,
    data: DocumentApproveUpdate,
    db: Session = Depends(get_session),
) -> GeneratedDocument:
    """Approve or reject a generated document before form filling."""
    app = db.scalar(
        select(Application)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    if app is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")

    policy = get_policy_config(db)
    doc = next((d for d in app.documents if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    if data.approved and policy.require_doc_approval:
        if doc.ats_score is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document has not passed ATS critique yet",
            )

    doc.approved = data.approved
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/{application_id}/apply", response_model=ApplicationApplyResponse)
async def apply_application(
    application_id: int,
    dry_run: bool = Query(default=True),
    submit_approved: bool = Query(default=False),
    db: Session = Depends(get_session),
) -> ApplicationApplyResponse:
    """Run browser form fill for an application (dry_run skips submit)."""
    try:
        result = await run_application_apply(
            db,
            application_id,
            dry_run=dry_run,
            submit_approved=submit_approved,
        )
    except ApprovalGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApplyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ApplicationApplyResponse(
        application_id=result.application_id,
        status=result.status,
        result=result.result.value,
        fields_filled=result.fields_filled,
        message=result.message,
        screenshot_path=result.screenshot_path,
        page_url=result.page_url,
        dry_run=result.dry_run,
        submitted=result.submitted,
    )
