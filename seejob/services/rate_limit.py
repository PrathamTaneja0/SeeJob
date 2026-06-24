"""Per-platform daily apply rate limiting via AgentRun audit log."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seejob.models.agent import AgentRun, AgentRunStatus
from seejob.models.policy import PolicyConfig
from seejob.services.policy import get_or_create_policy, get_platform_daily_limit


class RateLimitExceeded(Exception):
    """Raised when a platform or global daily apply cap is exceeded."""

    def __init__(self, platform: str, limit: int, count: int) -> None:
        self.platform = platform
        self.limit = limit
        self.count = count
        super().__init__(
            f"Daily apply limit reached for '{platform}': {count}/{limit}"
        )


@dataclass
class RateLimitStatus:
    """Current usage against configured limits."""

    platform: str
    limit: int
    count: int
    global_limit: int
    global_count: int

    @property
    def allowed(self) -> bool:
        return self.count < self.limit and self.global_count < self.global_limit


_COUNTABLE_STATUSES = frozenset(
    {
        AgentRunStatus.PENDING,
        AgentRunStatus.RUNNING,
        AgentRunStatus.COMPLETED,
    }
)


def _today_start_iso() -> str:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def _platform_from_summary(input_summary: str | None) -> str | None:
    if not input_summary:
        return None
    try:
        data = json.loads(input_summary)
    except json.JSONDecodeError:
        return None
    platform = data.get("platform")
    return str(platform).lower() if platform else None


def count_applies_today(db: Session, *, platform: str | None = None) -> int:
    """Count reserved or completed apply runs since UTC midnight."""
    today_start = _today_start_iso()
    if platform is not None:
        platform_lower = platform.lower()
        rows = db.scalars(
            select(AgentRun.input_summary).where(
                AgentRun.task_type == "apply",
                AgentRun.status.in_(_COUNTABLE_STATUSES),
                AgentRun.started_at >= today_start,
            )
        ).all()
        return sum(1 for summary in rows if _platform_from_summary(summary) == platform_lower)

    stmt = (
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.task_type == "apply",
            AgentRun.status.in_(_COUNTABLE_STATUSES),
            AgentRun.started_at >= today_start,
        )
    )
    return db.scalar(stmt) or 0


def get_rate_limit_status(db: Session, platform: str) -> RateLimitStatus:
    """Return usage vs limits for a platform."""
    policy = get_or_create_policy(db)
    platform_key = (platform or "default").lower()
    limit = get_platform_daily_limit(db, platform_key)
    count = count_applies_today(db, platform=platform_key)
    global_count = count_applies_today(db)
    return RateLimitStatus(
        platform=platform_key,
        limit=limit,
        count=count,
        global_limit=policy.daily_apply_limit,
        global_count=global_count,
    )


def check_rate_limit(db: Session, platform: str) -> RateLimitStatus:
    """Validate apply is allowed; raise RateLimitExceeded when capped."""
    status = get_rate_limit_status(db, platform)
    if not status.allowed:
        exceeded_limit = status.limit if status.count >= status.limit else status.global_limit
        exceeded_count = status.count if status.count >= status.limit else status.global_count
        raise RateLimitExceeded(status.platform, exceeded_limit, exceeded_count)
    return status


def _lock_policy_row(db: Session) -> None:
    """Serialize apply reservations against the policy row."""
    policy = get_or_create_policy(db)
    db.execute(
        select(PolicyConfig.id).where(PolicyConfig.id == policy.id).with_for_update()
    )


def reserve_apply_slot(
    db: Session,
    *,
    application_id: int,
    platform: str,
) -> AgentRun:
    """Atomically verify headroom and insert a pending apply run."""
    platform_key = (platform or "default").lower()
    _lock_policy_row(db)

    status = get_rate_limit_status(db, platform_key)
    if not status.allowed:
        exceeded_limit = status.limit if status.count >= status.limit else status.global_limit
        exceeded_count = status.count if status.count >= status.limit else status.global_count
        raise RateLimitExceeded(status.platform, exceeded_limit, exceeded_count)

    now = datetime.now(UTC).isoformat()
    run = AgentRun(
        worker_name="apply",
        task_type="apply",
        status=AgentRunStatus.PENDING,
        input_summary=json.dumps(
            {"application_id": application_id, "platform": platform_key}
        ),
        started_at=now,
    )
    db.add(run)
    db.flush()

    status = get_rate_limit_status(db, platform_key)
    if status.count > status.limit or status.global_count > status.global_limit:
        run.status = AgentRunStatus.CANCELLED
        run.finished_at = now
        db.flush()
        exceeded_limit = status.limit if status.count > status.limit else status.global_limit
        exceeded_count = status.count if status.count > status.limit else status.global_count
        raise RateLimitExceeded(status.platform, exceeded_limit, exceeded_count)

    return run


def finalize_apply_run(
    db: Session,
    run: AgentRun,
    *,
    success: bool,
    message: str | None = None,
) -> AgentRun:
    """Mark a reserved apply run as completed or failed."""
    now = datetime.now(UTC).isoformat()
    run.status = AgentRunStatus.COMPLETED if success else AgentRunStatus.FAILED
    run.output_summary = message
    run.finished_at = now
    db.flush()
    return run


def record_apply_run(
    db: Session,
    *,
    application_id: int,
    platform: str,
    success: bool,
    message: str | None = None,
) -> AgentRun:
    """Persist a completed apply attempt in AgentRun for rate-limit accounting."""
    now = datetime.now(UTC).isoformat()
    run = AgentRun(
        worker_name="pipeline",
        task_type="apply",
        status=AgentRunStatus.COMPLETED if success else AgentRunStatus.FAILED,
        input_summary=json.dumps({"application_id": application_id, "platform": platform.lower()}),
        output_summary=message,
        started_at=now,
        finished_at=now,
    )
    db.add(run)
    db.flush()
    return run
