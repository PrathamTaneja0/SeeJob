"""Job listing endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.models.job import Job, JobStatus
from seejob.schemas.job import JobCreate, JobRead

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


@router.post("", response_model=JobRead, status_code=201)
def create_job(data: JobCreate, db: Session = Depends(get_session)) -> Job:
    """Register a newly discovered job."""
    job = Job(**data.model_dump(mode="json"))
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_session)) -> Job:
    """Get a job by ID."""
    from fastapi import HTTPException

    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job
