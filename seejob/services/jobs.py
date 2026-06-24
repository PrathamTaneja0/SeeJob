"""Job review queue and application bootstrap."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seejob.models.application import Application, ApplicationStatus
from seejob.models.job import Job, JobStatus
from seejob.models.policy import PolicyConfig
from seejob.models.person import Person
from seejob.schemas.job import JobQueueBucket, JobQueueView
from seejob.services.profile import get_person
from seejob.services.state_machine import transition


class JobReviewError(ValueError):
    """Raised when a job review action is invalid."""


_QUEUE_BUCKETS: dict[str, JobStatus] = {
    "to_review": JobStatus.NEW,
    "approved": JobStatus.REVIEWED,
    "skipped": JobStatus.REJECTED,
    "applied": JobStatus.APPLIED,
}


def get_job_queue(db: Session, *, limit_per_bucket: int = 50) -> JobQueueView:
    """Return kanban buckets for the job review dashboard."""
    buckets: dict[str, JobQueueBucket] = {}
    for bucket_name, status in _QUEUE_BUCKETS.items():
        count = db.scalar(select(func.count()).select_from(Job).where(Job.status == status)) or 0
        jobs = list(
            db.scalars(
                select(Job)
                .where(Job.status == status)
                .order_by(Job.updated_at.desc())
                .limit(limit_per_bucket)
            ).all()
        )
        buckets[bucket_name] = JobQueueBucket(bucket=bucket_name, count=count, jobs=jobs)

    return JobQueueView(
        to_review=buckets["to_review"],
        approved=buckets["approved"],
        skipped=buckets["skipped"],
        applied=buckets["applied"],
    )


def _initial_application_status(policy: PolicyConfig) -> ApplicationStatus:
    """Pick pipeline entry state when a job is approved for a person."""
    if policy.auto_apply:
        return ApplicationStatus.DOCS_READY
    return ApplicationStatus.PENDING_APPROVAL


def bootstrap_application(
    db: Session,
    job: Job,
    person: Person,
    *,
    policy: PolicyConfig,
) -> Application:
    """Create or return application when a job is approved for a person."""
    existing = db.scalar(
        select(Application).where(
            Application.person_id == person.id,
            Application.job_id == job.id,
        )
    )
    if existing is not None:
        return existing

    target_status = _initial_application_status(policy)
    app = Application(
        person_id=person.id,
        job_id=job.id,
        status=ApplicationStatus.DISCOVERED,
    )
    db.add(app)
    db.flush()

    if target_status != ApplicationStatus.DISCOVERED:
        app.status = transition(ApplicationStatus.DISCOVERED, ApplicationStatus.SCORED)
        if target_status == ApplicationStatus.PENDING_APPROVAL:
            app.status = transition(app.status, ApplicationStatus.PENDING_APPROVAL)
        elif target_status == ApplicationStatus.DOCS_READY:
            app.status = transition(app.status, ApplicationStatus.PENDING_APPROVAL)
            app.status = transition(app.status, ApplicationStatus.GENERATING_DOCS)
            app.status = transition(app.status, ApplicationStatus.DOCS_READY)

    db.commit()
    db.refresh(app)
    return app


def approve_job(
    db: Session,
    job: Job,
    *,
    person_id: int,
    policy: PolicyConfig,
) -> tuple[Job, Application | None]:
    """Move job from review queue to approved and bootstrap application."""
    if job.status != JobStatus.NEW:
        raise JobReviewError(
            f"Job must be in 'new' status to approve (current: {job.status.value})"
        )

    person = get_person(db, person_id)
    job.status = JobStatus.REVIEWED
    db.flush()

    application = bootstrap_application(db, job, person, policy=policy)
    db.commit()
    db.refresh(job)
    return job, application


def skip_job(db: Session, job: Job) -> Job:
    """Skip a job in the review queue."""
    if job.status not in {JobStatus.NEW, JobStatus.REVIEWED}:
        raise JobReviewError(
            f"Job cannot be skipped from status '{job.status.value}'"
        )
    job.status = JobStatus.REJECTED
    db.commit()
    db.refresh(job)
    return job
