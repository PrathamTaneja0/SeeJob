"""Job discovery and scoring models."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.application import Application


class JobStatus(str, enum.Enum):
    """Lifecycle status for discovered jobs."""

    NEW = "new"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"
    APPLIED = "applied"
    REJECTED = "rejected"


class Job(Base, TimestampMixin):
    """Discovered job posting with fit scoring."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    jd_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    fit_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        default=JobStatus.NEW,
        nullable=False,
        index=True,
    )

    applications: Mapped[list["Application"]] = relationship(back_populates="job")
