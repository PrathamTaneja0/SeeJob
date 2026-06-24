"""Tests for per-platform daily apply rate limiting."""

from __future__ import annotations

import pytest

from seejob.models.policy import PolicyConfig
from seejob.services.rate_limit import (
    RateLimitExceeded,
    check_rate_limit,
    count_applies_today,
    get_rate_limit_status,
    record_apply_run,
)


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": False,
        "require_doc_approval": True,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "ats_min_score": 0.7,
        "daily_apply_limit": 5,
        "rate_limits_json": '{"default": 3, "greenhouse": 2, "linkedin": 1}',
        "blocked_companies_json": "[]",
        "blocked_keywords_json": "[]",
        "sourcing_enabled": True,
        "sourcing_schedule": "0 8 * * *",
        "sourcing_interval_minutes": 60,
    }
    defaults.update(overrides)
    policy = PolicyConfig(**defaults)
    db_session.add(policy)
    db_session.commit()
    return policy


def test_get_rate_limit_status_uses_platform_limit(db_session) -> None:
    _seed_policy(db_session)
    status = get_rate_limit_status(db_session, "greenhouse")
    assert status.platform == "greenhouse"
    assert status.limit == 2
    assert status.count == 0
    assert status.allowed


def test_record_apply_run_increments_platform_count(db_session) -> None:
    _seed_policy(db_session)
    record_apply_run(
        db_session,
        application_id=1,
        platform="greenhouse",
        success=True,
    )
    db_session.commit()
    assert count_applies_today(db_session, platform="greenhouse") == 1
    assert count_applies_today(db_session) == 1


def test_check_rate_limit_blocks_platform_cap(db_session) -> None:
    _seed_policy(db_session)
    record_apply_run(
        db_session,
        application_id=1,
        platform="linkedin",
        success=True,
    )
    db_session.commit()

    with pytest.raises(RateLimitExceeded) as exc_info:
        check_rate_limit(db_session, "linkedin")
    assert exc_info.value.platform == "linkedin"
    assert exc_info.value.limit == 1


def test_check_rate_limit_blocks_global_cap(db_session) -> None:
    _seed_policy(db_session, daily_apply_limit=2, rate_limits_json='{"default": 10}')
    for i in range(2):
        record_apply_run(
            db_session,
            application_id=i + 1,
            platform="lever",
            success=True,
        )
    db_session.commit()

    with pytest.raises(RateLimitExceeded):
        check_rate_limit(db_session, "lever")


def test_other_platforms_remain_allowed(db_session) -> None:
    _seed_policy(db_session)
    record_apply_run(
        db_session,
        application_id=1,
        platform="greenhouse",
        success=True,
    )
    db_session.commit()

    status = check_rate_limit(db_session, "workday")
    assert status.allowed
    assert status.limit == 3
