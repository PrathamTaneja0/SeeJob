"""Application pipeline schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from seejob.models.application import ApplicationStatus, DocumentType


class GeneratedDocumentRead(BaseModel):
    """Generated document preview for approval gates."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_type: DocumentType
    markdown_content: str
    pdf_path: str | None
    ats_score: float | None
    critic_report: str | None
    version: int
    approved: bool
    created_at: datetime


class ApplicationRead(BaseModel):
    """Application pipeline item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    job_id: int
    status: ApplicationStatus
    status_message: str | None
    platform: str | None
    submitted_at: str | None
    created_at: datetime
    updated_at: datetime
    documents: list[GeneratedDocumentRead] = []


class ApplicationPipelineView(BaseModel):
    """Grouped pipeline view by status."""

    status: ApplicationStatus
    count: int
    applications: list[ApplicationRead]


class ApplicationStatusUpdate(BaseModel):
    """Request to transition application status."""

    target_status: ApplicationStatus
    message: str | None = None
