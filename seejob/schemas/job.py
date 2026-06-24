"""Job schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from seejob.models.job import JobStatus


class JobBase(BaseModel):
    """Shared job fields."""

    url: HttpUrl | str
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = None
    is_remote: bool = False
    jd_text: str | None = None
    source: str = Field(min_length=1, max_length=100)
    fit_score: float | None = Field(default=None, ge=0, le=1)
    match_rationale: str | None = None


class JobCreate(JobBase):
    """Create a discovered job."""


class JobRead(JobBase):
    """Job response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: JobStatus
    created_at: datetime
    updated_at: datetime


class JobListParams(BaseModel):
    """Query parameters for job listing."""

    status: JobStatus | None = None
    source: str | None = None
    company: str | None = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class JobIngestUrl(BaseModel):
    """Manual job URL ingestion request."""

    url: HttpUrl | str
    person_id: int | None = Field(
        default=None,
        description="Optional person to score against after ingestion",
    )


class JobScoreRequest(BaseModel):
    """Trigger semantic scoring for a job."""

    person_id: int


class JobStatusAction(BaseModel):
    """Approve or skip a job in the review queue."""

    action: Literal["approve", "skip"]
    person_id: int | None = Field(
        default=None,
        description="Required when action is approve — creates application pipeline entry",
    )


class JobQueueBucket(BaseModel):
    """Kanban bucket for job review queue."""

    bucket: str
    count: int
    jobs: list[JobRead]


class JobQueueView(BaseModel):
    """Dashboard queue with kanban buckets."""

    to_review: JobQueueBucket
    approved: JobQueueBucket
    skipped: JobQueueBucket
    applied: JobQueueBucket
