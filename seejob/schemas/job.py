"""Job schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from seejob.models.job import JobStatus


class JobBase(BaseModel):
    """Shared job fields."""

    url: HttpUrl | str
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = None
    jd_text: str | None = None
    source: str = Field(min_length=1, max_length=100)
    fit_score: float | None = Field(default=None, ge=0, le=1)


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
