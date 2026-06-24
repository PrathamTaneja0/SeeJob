"""Sourcing pipeline — ingest, dedupe, filter, persist."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seejob.models.job import Job, JobStatus, hash_job_url, normalize_job_url
from seejob.models.policy import PolicyConfig
from seejob.schemas.policy import JobFilters, PolicyConfigDBFields
from seejob.services.policy import get_policy_config
from seejob.services.scoring import score_job
from seejob.services.sourcing.base import JobSource, RawJob
from seejob.services.sourcing.filters import apply_hard_filters
from seejob.services.sourcing.sources.board_api import BoardApiSource
from seejob.services.sourcing.sources.rss import RssJobSource

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of ingesting one raw job."""

    job: Job | None = None
    created: bool = False
    duplicate: bool = False
    filtered: bool = False
    filter_reason: str | None = None


@dataclass
class SourcingRunResult:
    """Summary of a sourcing tick."""

    sources_polled: int = 0
    fetched: int = 0
    created: int = 0
    duplicates: int = 0
    filtered: int = 0
    scored: int = 0
    archived: int = 0
    errors: list[str] = field(default_factory=list)


def _policy_filters(policy: PolicyConfig) -> tuple[JobFilters | None, list[str], list[str]]:
    job_filters = PolicyConfigDBFields.loads_job_filters(policy.job_filters_json)
    blocked_companies = PolicyConfigDBFields.loads_list(policy.blocked_companies_json)
    blocked_keywords = PolicyConfigDBFields.loads_list(policy.blocked_keywords_json)
    return job_filters, blocked_companies, blocked_keywords


def ingest_raw_job(
    db: Session,
    raw: RawJob,
    *,
    policy: PolicyConfig | None = None,
    apply_filters: bool = True,
    person_id: int | None = None,
    score_after_ingest: bool = False,
) -> IngestResult:
    """Persist a raw job with deduplication and optional hard filters."""
    policy = policy or get_policy_config(db)
    url = normalize_job_url(raw.url)
    url_hash = hash_job_url(url)

    existing = db.scalar(select(Job).where(Job.url_hash == url_hash))
    if existing is None:
        existing = db.scalar(select(Job).where(Job.url == url))
    if existing is not None:
        return IngestResult(job=existing, duplicate=True)

    if apply_filters:
        job_filters, blocked_companies, blocked_keywords = _policy_filters(policy)
        filter_result = apply_hard_filters(
            raw,
            job_filters=job_filters,
            blocked_companies=blocked_companies,
            blocked_keywords=blocked_keywords,
        )
        if not filter_result.passed:
            return IngestResult(
                filtered=True,
                filter_reason=filter_result.reason,
            )

    job = Job(
        url=url,
        url_hash=url_hash,
        title=raw.title,
        company=raw.company,
        location=raw.location,
        is_remote=raw.is_remote,
        jd_text=raw.jd_text,
        source=raw.source,
        status=JobStatus.NEW,
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
    except IntegrityError:
        db.rollback()
        dup = db.scalar(select(Job).where(Job.url_hash == url_hash))
        return IngestResult(job=dup, duplicate=True)

    if score_after_ingest and person_id is not None:
        score_job(db, job, person_id, policy=policy)

    return IngestResult(job=job, created=True)


async def run_sourcing_pipeline(
    db: Session,
    sources: list[JobSource],
    *,
    person_id: int | None = None,
) -> SourcingRunResult:
    """Fetch from all sources, filter, dedupe, score, and archive low-fit jobs."""
    policy = get_policy_config(db)
    result = SourcingRunResult(sources_polled=len(sources))

    if not policy.sourcing_enabled:
        result.errors.append("sourcing disabled in policy")
        return result

    for source in sources:
        try:
            raw_jobs = await source.fetch_new_jobs()
        except Exception as exc:
            logger.exception("Source %s failed", source.name)
            result.errors.append(f"{source.name}: {exc}")
            continue

        result.fetched += len(raw_jobs)
        for raw in raw_jobs:
            ingest = ingest_raw_job(
                db,
                raw,
                policy=policy,
                person_id=person_id,
                score_after_ingest=person_id is not None,
            )
            if ingest.duplicate:
                result.duplicates += 1
                continue
            if ingest.filtered:
                result.filtered += 1
                continue
            if ingest.created and ingest.job is not None:
                result.created += 1
                if ingest.job.fit_score is not None:
                    result.scored += 1
                    if ingest.job.status == JobStatus.ARCHIVED:
                        result.archived += 1

    return result


def build_policy_sources(policy: PolicyConfig) -> list[JobSource]:
    """Build RSS and board API sources from policy configuration."""
    sources: list[JobSource] = []
    feeds = PolicyConfigDBFields.loads_list(policy.rss_feeds_json)
    if feeds:
        sources.append(RssJobSource(feeds, enrich_html=False))
    sources.append(BoardApiSource())
    return sources
