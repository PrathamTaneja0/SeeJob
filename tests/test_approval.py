"""Tests for approval gate service logic."""

import pytest

from seejob.models.application import Application, ApplicationStatus, DocumentType, GeneratedDocument
from seejob.models.policy import PolicyConfig
from seejob.services.approval import ApprovalGateError, validate_approval_gates


def _policy(**overrides) -> PolicyConfig:
    return PolicyConfig(
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
        **overrides,
    )


def _app(*, approved: bool) -> Application:
    app = Application(id=1, person_id=1, job_id=1, status=ApplicationStatus.DOCS_READY)
    app.documents = [
        GeneratedDocument(
            application_id=1,
            doc_type=DocumentType.CV,
            markdown_content="# CV",
            approved=approved,
        )
    ]
    return app


def test_validate_doc_gate_blocks_unapproved() -> None:
    with pytest.raises(ApprovalGateError, match="Document approval required"):
        validate_approval_gates(_app(approved=False), _policy(), ApplicationStatus.FILLING)


def test_validate_submit_gate_blocks_without_flag() -> None:
    with pytest.raises(ApprovalGateError, match="Submit approval required"):
        validate_approval_gates(
            _app(approved=True),
            _policy(),
            ApplicationStatus.SUBMITTED,
        )
