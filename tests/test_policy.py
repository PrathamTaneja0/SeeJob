"""Tests for policy singleton get-or-create."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from seejob.models.policy import PolicyConfig
from seejob.services.policy import _ensure_policy_row


def test_ensure_policy_row_retries_on_integrity_error(db_session) -> None:
    """Concurrent first inserts recover via integrity-error retry."""
    existing = PolicyConfig(
        id=1,
        auto_apply=False,
        require_doc_approval=True,
        require_submit_approval=True,
        min_fit_score=0.6,
        ats_min_score=0.7,
        daily_apply_limit=10,
        rate_limits_json='{"default": 10}',
        blocked_companies_json="[]",
        blocked_keywords_json="[]",
        sourcing_enabled=True,
        sourcing_schedule="0 8 * * *",
    )
    db_session.add(existing)
    db_session.commit()

    original_commit = db_session.commit

    def commit_once_then_fail() -> None:
        if not getattr(commit_once_then_fail, "called", False):
            commit_once_then_fail.called = True  # type: ignore[attr-defined]
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

        original_commit()

    db_session.commit = MagicMock(side_effect=commit_once_then_fail)  # type: ignore[method-assign]

    policy = _ensure_policy_row(db_session)
    assert policy.id == 1
    assert policy.require_doc_approval is True
