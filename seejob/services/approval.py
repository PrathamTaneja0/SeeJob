"""Approval gate enforcement for application status transitions."""

from seejob.models.application import Application, ApplicationStatus, GeneratedDocument
from seejob.models.policy import PolicyConfig


class ApprovalGateError(ValueError):
    """Raised when a policy approval gate blocks a status transition."""


def _documents_approved(documents: list[GeneratedDocument]) -> bool:
    """Return True when every generated document is human-approved."""
    return bool(documents) and all(doc.approved for doc in documents)


def validate_approval_gates(
    app: Application,
    policy: PolicyConfig,
    target_status: ApplicationStatus,
    *,
    submit_approved: bool = False,
) -> None:
    """Enforce PolicyConfig approval gates before sensitive transitions."""
    if policy.auto_apply:
        return

    if target_status == ApplicationStatus.FILLING and policy.require_doc_approval:
        if not _documents_approved(app.documents):
            raise ApprovalGateError(
                "Document approval required before filling. "
                "Approve all generated documents or disable require_doc_approval."
            )

    if target_status == ApplicationStatus.SUBMITTED and policy.require_submit_approval:
        if not submit_approved:
            raise ApprovalGateError(
                "Submit approval required. Set submit_approved=true to confirm submission."
            )
