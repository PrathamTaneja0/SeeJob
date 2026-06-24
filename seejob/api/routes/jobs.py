"""Job listing and review queue endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.models.job import Job, JobStatus
from seejob.schemas.job import (
    JobCreate,
    JobIngestUrl,
    JobQueueView,
    JobRead,
    JobScoreRequest,
    JobStatusAction,
)
from seejob.services.jobs import JobReviewError, approve_job, get_job_queue, skip_job
from seejob.services.policy import get_policy_config
from seejob.services.scoring import score_job
from seejob.services.sourcing.pipeline import ingest_raw_job
from seejob.services.sourcing.sources.manual import ManualUrlSource

router = APIRouter()


@router.get("", response_model=list[JobRead])
def list_jobs(
    status: JobStatus | None = Query(default=None),
    source: str | None = Query(default=None),
    company: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> list[Job]:
    """List discovered jobs with optional status and source filters."""
    stmt = select(Job).order_by(Job.created_at.desc())
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if source is not None:
        stmt = stmt.where(Job.source == source)
    if company is not None:
        stmt = stmt.where(Job.company.ilike(f"%{company}%"))
    stmt = stmt.offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/queue", response_model=JobQueueView)
def job_queue(db: Session = Depends(get_session)) -> JobQueueView:
    """Kanban buckets: to_review, approved, skipped, applied."""
    return get_job_queue(db)


@router.post("/ingest-url", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def ingest_job_url(data: JobIngestUrl, db: Session = Depends(get_session)) -> Job:
    """Manually add a job by scraping its posting URL."""
    source = ManualUrlSource(str(data.url))
    try:
        raw_jobs = await source.fetch_new_jobs()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch job URL: {exc}",
        ) from exc

    if not raw_jobs:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No job parsed")

    result = ingest_raw_job(
        db,
        raw_jobs[0],
        person_id=data.person_id,
        score_after_ingest=data.person_id is not None,
    )
    if result.duplicate and result.job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job already exists (id={result.job.id})",
        )
    if result.filtered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.filter_reason or "Job blocked by hard filters",
        )
    if result.job is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ingest failed")

    return result.job


@router.post("", response_model=JobRead, status_code=201)
def create_job(data: JobCreate, db: Session = Depends(get_session)) -> Job:
    """Register a newly discovered job."""
    from seejob.models.job import hash_job_url, normalize_job_url
    from seejob.services.sourcing.base import RawJob

    raw = RawJob(
        url=str(data.url),
        title=data.title,
        company=data.company,
        location=data.location,
        is_remote=data.is_remote,
        jd_text=data.jd_text,
        source=data.source,
    )
    result = ingest_raw_job(db, raw, apply_filters=False)
    if result.duplicate and result.job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job already exists (id={result.job.id})",
        )
    if result.job is None:
        job = Job(
            url=normalize_job_url(str(data.url)),
            url_hash=hash_job_url(str(data.url)),
            title=data.title,
            company=data.company,
            location=data.location,
            is_remote=data.is_remote,
            jd_text=data.jd_text,
            source=data.source,
            fit_score=data.fit_score,
            match_rationale=data.match_rationale,
            status=JobStatus.NEW,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    if data.fit_score is not None:
        result.job.fit_score = data.fit_score
    if data.match_rationale is not None:
        result.job.match_rationale = data.match_rationale
    db.commit()
    db.refresh(result.job)
    return result.job


@router.post("/{job_id}/score", response_model=JobRead)
def trigger_job_score(
    job_id: int,
    data: JobScoreRequest,
    db: Session = Depends(get_session),
) -> Job:
    """Trigger semantic scoring for a job against a person profile."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    try:
        score_job(db, job, data.person_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    db.refresh(job)
    return job


@router.patch("/{job_id}/status", response_model=JobRead)
def update_job_status(
    job_id: int,
    data: JobStatusAction,
    db: Session = Depends(get_session),
) -> Job:
    """Approve (pending review → approved) or skip a job in the review queue."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    policy = get_policy_config(db)

    try:
        if data.action == "approve":
            if data.person_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="person_id is required when approving a job",
                )
            job, _app = approve_job(db, job, person_id=data.person_id, policy=policy)
            return job
        job = skip_job(db, job)
        return job
    except JobReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_session)) -> Job:
    """Get a job by ID."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job
