"""Policy configuration schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RateLimits(BaseModel):
    """Per-platform daily application rate limits."""

    default: int = Field(default=10, ge=0)
    linkedin: int | None = Field(default=None, ge=0)
    greenhouse: int | None = Field(default=None, ge=0)
    lever: int | None = Field(default=None, ge=0)
    workday: int | None = Field(default=None, ge=0)
    icims: int | None = Field(default=None, ge=0)

    def get_limit(self, platform: str) -> int:
        """Return platform-specific limit or default."""
        value = getattr(self, platform.lower(), None)
        return value if value is not None else self.default


class JobFilters(BaseModel):
    """Job discovery filters."""

    min_fit_score: float | None = Field(default=None, ge=0, le=1)
    remote_only: bool = False
    locations: list[str] = Field(default_factory=list)
    titles_include: list[str] = Field(default_factory=list)
    titles_exclude: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    seniority_exclude: list[str] = Field(
        default_factory=lambda: ["senior", "staff", "principal", "director", "vp", "head of"]
    )


class PolicyConfigRead(BaseModel):
    """Policy configuration response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    auto_apply: bool
    require_doc_approval: bool
    require_submit_approval: bool
    min_fit_score: float
    ats_min_score: float = 0.7
    daily_apply_limit: int
    rate_limits: RateLimits
    job_filters: JobFilters | None
    blocked_companies: list[str]
    blocked_keywords: list[str]
    sourcing_enabled: bool
    sourcing_schedule: str
    rss_feeds: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PolicyConfigUpdate(BaseModel):
    """Partial policy update."""

    auto_apply: bool | None = None
    require_doc_approval: bool | None = None
    require_submit_approval: bool | None = None
    min_fit_score: float | None = Field(default=None, ge=0, le=1)
    ats_min_score: float | None = Field(default=None, ge=0, le=1)
    daily_apply_limit: int | None = Field(default=None, ge=0)
    rate_limits: RateLimits | None = None
    job_filters: JobFilters | None = None
    blocked_companies: list[str] | None = None
    blocked_keywords: list[str] | None = None
    sourcing_enabled: bool | None = None
    sourcing_schedule: str | None = None
    rss_feeds: list[str] | None = None


class PolicyConfigDBFields(BaseModel):
    """Internal helper for JSON field serialization."""

    rate_limits_json: str
    job_filters_json: str | None
    blocked_companies_json: str | None
    blocked_keywords_json: str | None

    @staticmethod
    def dumps_rate_limits(rate_limits: RateLimits) -> str:
        import json

        return json.dumps(rate_limits.model_dump(exclude_none=True))

    @staticmethod
    def dumps_job_filters(filters: JobFilters | None) -> str | None:
        if filters is None:
            return None
        import json

        return json.dumps(filters.model_dump())

    @staticmethod
    def dumps_list(items: list[str] | None) -> str | None:
        if items is None:
            return None
        import json

        return json.dumps(items)

    @staticmethod
    def loads_rate_limits(raw: str) -> RateLimits:
        import json

        data: dict[str, Any] = json.loads(raw)
        return RateLimits(**data)

    @staticmethod
    def loads_job_filters(raw: str | None) -> JobFilters | None:
        if not raw:
            return None
        import json

        return JobFilters(**json.loads(raw))

    @staticmethod
    def loads_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        import json

        return json.loads(raw)

    @staticmethod
    def dumps_rss_feeds(feeds: list[str] | None) -> str | None:
        if feeds is None:
            return None
        import json

        return json.dumps(feeds)
