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
    interrupt_metadata_json: str | None = None
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
    submit_approved: bool = False


class ApplicationDocumentsView(BaseModel):
    """Preview of generated documents with ATS reports."""

    application_id: int
    status: ApplicationStatus
    documents: list[GeneratedDocumentRead]


class DocumentApproveUpdate(BaseModel):
    """Approve a generated document for form filling."""

    approved: bool = True


class DocumentGenerationResponse(BaseModel):
    """Response after triggering document generation."""

    application_id: int
    status: ApplicationStatus
    documents: list[GeneratedDocumentRead]
    message: str | None = None


class ApplicationApplyResponse(BaseModel):
    """Response after browser apply orchestration."""

    application_id: int
    status: ApplicationStatus
    result: str
    fields_filled: int
    message: str | None = None
    screenshot_path: str | None = None
    page_url: str | None = None
    dry_run: bool
    submitted: bool = False


class ApplicationResumeRequest(BaseModel):
    """Optional note when resuming from an interrupt."""

    note: str | None = None


class ApplicationResumeResponse(BaseModel):
    """Response after resuming from needs_manual or auth_required."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ApplicationStatus
    status_message: str | None
    interrupt_metadata_json: str | None = None


class ApplicationProvideOtpRequest(BaseModel):
    """Manual OTP injection from dashboard during auth_required."""

    otp: str


class ApplicationProvideOtpResponse(BaseModel):
    """Confirmation after OTP is queued for login."""

    application_id: int
    message: str
