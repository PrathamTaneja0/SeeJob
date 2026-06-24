"""Job discovery and scoring models."""

import enum
import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from sqlalchemy import Boolean, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.application import Application


class JobStatus(str, enum.Enum):
    """Lifecycle status for discovered jobs."""

    NEW = "new"  # queue: to_review / pending_approval
    REVIEWED = "reviewed"  # queue: approved
    ARCHIVED = "archived"  # below fit threshold or filtered out
    APPLIED = "applied"  # queue: applied
    REJECTED = "rejected"  # queue: skipped


def normalize_job_url(url: str) -> str:
    """Normalize a job URL for deduplication."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def hash_job_url(url: str) -> str:
    """Return SHA-256 hex digest of normalized job URL."""
    return hashlib.sha256(normalize_job_url(url).encode("utf-8")).hexdigest()


class Job(Base, TimestampMixin):
    """Discovered job posting with fit scoring."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False, index=True)
    url_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jd_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    fit_score: Mapped[float | None] = mapped_column(Float)
    match_rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        default=JobStatus.NEW,
        nullable=False,
        index=True,
    )

    applications: Mapped[list["Application"]] = relationship(back_populates="job")
