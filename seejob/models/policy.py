"""Policy configuration for rate limits and automation rules."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from seejob.models.base import Base, TimestampMixin


class PolicyConfig(Base, TimestampMixin):
    """Singleton-style policy row (id=1) for automation behavior.

  rate_limits_json stores per-platform daily limits, e.g.
  {"linkedin": 5, "greenhouse": 10, "default": 3}
    """

    __tablename__ = "policy_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_doc_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_submit_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_fit_score: Mapped[float] = mapped_column(default=0.6, nullable=False)
    daily_apply_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    rate_limits_json: Mapped[str] = mapped_column(
        Text,
        default='{"default": 10}',
        nullable=False,
    )
    job_filters_json: Mapped[str | None] = mapped_column(Text)
    blocked_companies_json: Mapped[str | None] = mapped_column(Text)
    blocked_keywords_json: Mapped[str | None] = mapped_column(Text)
    sourcing_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sourcing_schedule: Mapped[str] = mapped_column(String(100), default="0 8 * * *", nullable=False)
