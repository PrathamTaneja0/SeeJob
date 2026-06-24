"""Application pipeline and generated documents."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.job import Job
    from seejob.models.person import Person


class ApplicationStatus(str, enum.Enum):
    """Application state machine statuses."""

    DISCOVERED = "discovered"
    SCORED = "scored"
    PENDING_APPROVAL = "pending_approval"
    GENERATING_DOCS = "generating_docs"
    DOCS_READY = "docs_ready"
    AUTH_REQUIRED = "auth_required"
    FILLING = "filling"
    SUBMITTED = "submitted"
    FAILED = "failed"
    NEEDS_MANUAL = "needs_manual"


class DocumentType(str, enum.Enum):
    """Types of generated application documents."""

    CV = "cv"
    COVER_LETTER = "cover_letter"
    OTHER = "other"


class Application(Base, TimestampMixin):
    """Job application with state-machine-driven lifecycle."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    status_message: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(100))
    submitted_at: Mapped[str | None] = mapped_column(String(50))

    person: Mapped["Person"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    documents: Mapped[list["GeneratedDocument"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )


class GeneratedDocument(Base, TimestampMixin):
    """Tailored CV or cover letter with truthfulness audit trail."""

    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
    )
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(1000))
    ats_score: Mapped[float | None] = mapped_column(Float)
    critic_report: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    approved: Mapped[bool] = mapped_column(default=False, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="documents")
