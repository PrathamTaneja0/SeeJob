"""Per-domain ATS procedural memory read/write."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.models.ats import ATSLearning


def normalize_domain(url: str) -> str:
    """Extract hostname from URL for ATS learning keys."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def get_domain_learnings(db: Session, domain: str) -> list[ATSLearning]:
    """Fetch all procedural notes for a domain."""
    return list(
        db.scalars(select(ATSLearning).where(ATSLearning.domain == domain).order_by(ATSLearning.id))
    )


def store_apply_learning(
    db: Session,
    *,
    domain: str,
    fields_filled: int,
    fields_failed: int,
    dry_run: bool,
    success: bool,
    notes: str | None = None,
) -> ATSLearning:
    """Upsert procedural notes after an apply attempt."""
    procedure_key = "form_fill"
    record = db.scalar(
        select(ATSLearning).where(
            ATSLearning.domain == domain,
            ATSLearning.procedure_key == procedure_key,
        )
    )

    payload = {
        "last_run": datetime.now(UTC).isoformat(),
        "fields_filled": fields_filled,
        "fields_failed": fields_failed,
        "dry_run": dry_run,
        "success": success,
    }
    if notes:
        payload["notes"] = notes

    if record is None:
        record = ATSLearning(
            domain=domain,
            procedure_key=procedure_key,
            procedure_data=json.dumps(payload),
            success_count=1 if success else 0,
            failure_count=0 if success else 1,
            notes=notes,
        )
        db.add(record)
    else:
        existing = json.loads(record.procedure_data) if record.procedure_data else {}
        existing.update(payload)
        record.procedure_data = json.dumps(existing)
        if notes:
            record.notes = notes
        if success:
            record.success_count += 1
        else:
            record.failure_count += 1

    db.commit()
    db.refresh(record)
    return record
