"""Policy configuration service."""


from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seejob.models.policy import PolicyConfig
from seejob.schemas.policy import (
    JobFilters,
    PolicyConfigDBFields,
    PolicyConfigRead,
    PolicyConfigUpdate,
    RateLimits,
)


def _default_policy() -> PolicyConfig:
    """Return default policy values for initial seed."""
    return PolicyConfig(
        id=1,
        auto_apply=False,
        require_doc_approval=True,
        require_submit_approval=True,
        min_fit_score=0.6,
        ats_min_score=0.7,
        daily_apply_limit=10,
        rate_limits_json='{"default": 10}',
        job_filters_json=None,
        blocked_companies_json="[]",
        blocked_keywords_json="[]",
        sourcing_enabled=True,
        sourcing_schedule="0 8 * * *",
        sourcing_interval_minutes=60,
    )


def _to_read(policy: PolicyConfig) -> PolicyConfigRead:
    """Convert ORM model to API schema."""
    return PolicyConfigRead(
        id=policy.id,
        auto_apply=policy.auto_apply,
        require_doc_approval=policy.require_doc_approval,
        require_submit_approval=policy.require_submit_approval,
        min_fit_score=policy.min_fit_score,
        ats_min_score=policy.ats_min_score,
        daily_apply_limit=policy.daily_apply_limit,
        rate_limits=PolicyConfigDBFields.loads_rate_limits(policy.rate_limits_json),
        job_filters=PolicyConfigDBFields.loads_job_filters(policy.job_filters_json),
        blocked_companies=PolicyConfigDBFields.loads_list(policy.blocked_companies_json),
        blocked_keywords=PolicyConfigDBFields.loads_list(policy.blocked_keywords_json),
        sourcing_enabled=policy.sourcing_enabled,
        sourcing_schedule=policy.sourcing_schedule,
        sourcing_interval_minutes=policy.sourcing_interval_minutes,
        rss_feeds=PolicyConfigDBFields.loads_list(policy.rss_feeds_json),
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _ensure_policy_row(db: Session) -> PolicyConfig:
    """Return the singleton policy row, creating defaults if missing."""
    policy = db.scalar(select(PolicyConfig).where(PolicyConfig.id == 1))
    if policy is not None:
        return policy

    policy = _default_policy()
    db.add(policy)
    try:
        db.commit()
        db.refresh(policy)
        return policy
    except IntegrityError:
        db.rollback()
        policy = db.scalar(select(PolicyConfig).where(PolicyConfig.id == 1))
        if policy is None:
            raise
        return policy


def get_policy_config(db: Session) -> PolicyConfig:
    """Return the singleton policy ORM row."""
    return _ensure_policy_row(db)


def get_or_create_policy(db: Session) -> PolicyConfigRead:
    """Return the singleton policy config, creating defaults if missing."""
    return _to_read(_ensure_policy_row(db))


def update_policy(db: Session, data: PolicyConfigUpdate) -> PolicyConfigRead:
    """Update policy configuration fields."""
    policy = db.scalar(select(PolicyConfig).where(PolicyConfig.id == 1))
    if policy is None:
        policy = _default_policy()
        db.add(policy)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            policy = db.scalar(select(PolicyConfig).where(PolicyConfig.id == 1))
            if policy is None:
                raise

    payload = data.model_dump(exclude_unset=True)
    if "rate_limits" in payload and payload["rate_limits"] is not None:
        policy.rate_limits_json = PolicyConfigDBFields.dumps_rate_limits(
            RateLimits(**payload.pop("rate_limits"))
        )
    if "job_filters" in payload:
        filters = payload.pop("job_filters")
        policy.job_filters_json = (
            PolicyConfigDBFields.dumps_job_filters(JobFilters(**filters))
            if filters is not None
            else None
        )
    if "blocked_companies" in payload:
        policy.blocked_companies_json = PolicyConfigDBFields.dumps_list(
            payload.pop("blocked_companies")
        )
    if "blocked_keywords" in payload:
        policy.blocked_keywords_json = PolicyConfigDBFields.dumps_list(
            payload.pop("blocked_keywords")
        )
    if "rss_feeds" in payload:
        policy.rss_feeds_json = PolicyConfigDBFields.dumps_list(payload.pop("rss_feeds"))

    for field, value in payload.items():
        setattr(policy, field, value)

    db.commit()
    db.refresh(policy)
    return _to_read(policy)


def get_platform_daily_limit(db: Session, platform: str) -> int:
    """Return the configured daily apply limit for a platform."""
    policy = get_or_create_policy(db)
    return policy.rate_limits.get_limit(platform)
