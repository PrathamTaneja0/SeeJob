"""Tests for job sourcing, filtering, scoring, and queue endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from seejob.models.application import Application, ApplicationStatus
from seejob.models.job import Job, JobStatus, hash_job_url, normalize_job_url
from seejob.models.person import Person, WorkAuthorization
from seejob.models.policy import PolicyConfig
from seejob.schemas.policy import JobFilters
from seejob.services.jobs import get_job_queue
from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore
from seejob.services.scoring import score_job
from seejob.services.sourcing.base import RawJob
from seejob.services.sourcing.filters import apply_hard_filters
from seejob.services.sourcing.parser import parse_job_html
from seejob.services.sourcing.pipeline import ingest_raw_job
from seejob.services.sourcing.sources.manual import ManualUrlSource
from seejob.services.sourcing.sources.rss import RssJobSource

SAMPLE_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "JobPosting",
  "title": "Python Developer",
  "hiringOrganization": {"name": "Acme Corp"},
  "jobLocation": {"address": {"addressLocality": "Berlin", "addressCountry": "DE"}},
  "description": "Build APIs with Python and FastAPI. Remote friendly."
}
</script>
<title>Python Developer | Acme</title>
</head><body><h1>Python Developer</h1></body></html>
"""

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Jobs</title>
<item>
  <title>Backend Engineer</title>
  <link>https://jobs.example.com/backend-1</link>
  <description>Python and SQL required.</description>
</item>
</channel></rss>"""


def _seed_policy(db_session, **overrides) -> PolicyConfig:
    defaults = {
        "id": 1,
        "auto_apply": False,
        "require_doc_approval": True,
        "require_submit_approval": True,
        "min_fit_score": 0.6,
        "daily_apply_limit": 10,
        "rate_limits_json": '{"default": 10}',
        "blocked_companies_json": "[]",
        "blocked_keywords_json": "[]",
        "sourcing_enabled": True,
        "sourcing_schedule": "0 8 * * *",
        "rss_feeds_json": '["https://feeds.example.com/jobs.xml"]',
    }
    defaults.update(overrides)
    policy = PolicyConfig(**defaults)
    db_session.add(policy)
    db_session.commit()
    return policy


def _seed_person(db_session) -> Person:
    person = Person(
        full_name="Dev User",
        email="dev@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
        summary="Python developer with FastAPI experience",
    )
    db_session.add(person)
    db_session.commit()
    return person


def test_normalize_and_hash_url() -> None:
    """URL normalization is stable for deduplication."""
    a = normalize_job_url("https://Example.com/jobs/1/")
    b = normalize_job_url("https://example.com/jobs/1")
    assert a == b
    assert len(hash_job_url(a)) == 64


def test_parse_job_html_json_ld() -> None:
    """Parser extracts structured fields from JSON-LD."""
    parsed = parse_job_html(SAMPLE_HTML, "https://acme.com/jobs/1")
    assert parsed["title"] == "Python Developer"
    assert parsed["company"] == "Acme Corp"
    assert parsed["location"] == "Berlin, DE"
    assert parsed["is_remote"] is True
    assert "Python" in (parsed["jd_text"] or "")


def test_hard_filter_blocked_company() -> None:
    """Blocked companies are rejected deterministically."""
    job = RawJob(url="https://x.com/1", title="Engineer", company="EvilCo", source="test")
    result = apply_hard_filters(
        job,
        job_filters=None,
        blocked_companies=["EvilCo"],
        blocked_keywords=[],
    )
    assert result.passed is False
    assert "blocked company" in (result.reason or "")


def test_hard_filter_must_have_skills() -> None:
    """Must-have skills are enforced on JD text."""
    job = RawJob(
        url="https://x.com/2",
        title="Engineer",
        company="GoodCo",
        jd_text="We use Java and Spring.",
        source="test",
    )
    filters = JobFilters(must_have_skills=["python"])
    result = apply_hard_filters(
        job,
        job_filters=filters,
        blocked_companies=[],
        blocked_keywords=[],
    )
    assert result.passed is False
    assert "python" in (result.reason or "").lower()


def test_hard_filter_seniority_exclude() -> None:
    """Seniority keywords in title are blocked."""
    job = RawJob(url="https://x.com/3", title="Senior Python Engineer", company="Co", source="test")
    result = apply_hard_filters(
        job,
        job_filters=JobFilters(),
        blocked_companies=[],
        blocked_keywords=[],
    )
    assert result.passed is False


def test_ingest_deduplicates_by_url_hash(db_session) -> None:
    """Duplicate URLs are not inserted twice."""
    _seed_policy(db_session)
    raw = RawJob(
        url="https://jobs.example.com/role-1/",
        title="Dev",
        company="Co",
        source="manual",
    )
    first = ingest_raw_job(db_session, raw)
    second = ingest_raw_job(db_session, raw)
    assert first.created is True
    assert second.duplicate is True
    assert first.job is not None and second.job is not None
    assert first.job.id == second.job.id


@pytest.mark.asyncio
async def test_manual_url_source_mock_http() -> None:
    """ManualUrlSource parses HTML from mocked HTTP response."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=SAMPLE_HTML, request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        source = ManualUrlSource("https://acme.com/jobs/1", client=client)
        jobs = await source.fetch_new_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Python Developer"
    assert jobs[0].company == "Acme Corp"


@pytest.mark.asyncio
async def test_rss_source_mock_http() -> None:
    """RssJobSource parses feed entries without HTML enrichment."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=RSS_XML, request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        source = RssJobSource(["https://feeds.example.com/jobs.xml"], client=client, enrich_html=False)
        jobs = await source.fetch_new_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].url == "https://jobs.example.com/backend-1"


def test_score_job_with_hash_embeddings(db_session, tmp_path) -> None:
    """Scoring uses hash embeddings and stores fit_score."""
    _seed_policy(db_session, min_fit_score=0.5)
    person = _seed_person(db_session)
    store = VectorMemoryStore(
        persist_dir=tmp_path / "chroma",
        embedder=HashEmbedder(),
    )
    store.add_chunks(
        person.id,
        ["Python FastAPI backend developer with REST API experience"],
        chunk_type=ChunkType.CV,
    )

    job = Job(
        url="https://jobs.example.com/python",
        url_hash=hash_job_url("https://jobs.example.com/python"),
        title="Python Engineer",
        company="TechCo",
        jd_text="Looking for Python and FastAPI experience to build APIs.",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    result = score_job(db_session, job, person.id, memory_store=store)
    assert 0.0 <= result.fit_score <= 1.0
    assert result.match_rationale
    assert job.fit_score is not None


def test_score_below_threshold_archives(db_session, tmp_path) -> None:
    """Jobs below min_fit_score are archived."""
    _seed_policy(db_session, min_fit_score=0.99)
    person = _seed_person(db_session)
    store = VectorMemoryStore(persist_dir=tmp_path / "chroma2", embedder=HashEmbedder())

    job = Job(
        url="https://jobs.example.com/unrelated",
        url_hash=hash_job_url("https://jobs.example.com/unrelated"),
        title="Java Architect",
        company="LegacyCo",
        jd_text="Enterprise Java and COBOL maintenance.",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    score_job(db_session, job, person.id, memory_store=store)
    assert job.status == JobStatus.ARCHIVED


def test_job_queue_buckets(db_session) -> None:
    """Queue view groups jobs into kanban buckets."""
    jobs = [
        Job(
            url=f"https://example.com/{i}",
            url_hash=hash_job_url(f"https://example.com/{i}"),
            title=f"Role {i}",
            company="Co",
            source="test",
            status=status,
        )
        for i, status in enumerate(
            [JobStatus.NEW, JobStatus.REVIEWED, JobStatus.REJECTED, JobStatus.APPLIED]
        )
    ]
    db_session.add_all(jobs)
    db_session.commit()

    queue = get_job_queue(db_session)
    assert queue.to_review.count == 1
    assert queue.approved.count == 1
    assert queue.skipped.count == 1
    assert queue.applied.count == 1


def test_ingest_url_endpoint(client, db_session) -> None:
    """POST /jobs/ingest-url creates a job from mocked HTML."""
    _seed_policy(db_session)

    with patch.object(
        ManualUrlSource,
        "fetch_new_jobs",
        new=AsyncMock(
            return_value=[
                RawJob(
                    url="https://acme.com/jobs/1",
                    title="Python Dev",
                    company="Acme",
                    jd_text="Python role",
                    source="manual_url",
                )
            ]
        ),
    ):
        response = client.post(
            "/api/v1/jobs/ingest-url",
            json={"url": "https://acme.com/jobs/1"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Python Dev"
    assert data["company"] == "Acme"


def test_score_endpoint(client, db_session) -> None:
    """POST /jobs/{id}/score triggers scoring."""
    _seed_policy(db_session)
    person = _seed_person(db_session)
    job = Job(
        url="https://example.com/score-me",
        url_hash=hash_job_url("https://example.com/score-me"),
        title="Python Dev",
        company="Co",
        jd_text="Python FastAPI",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    response = client.post(
        f"/api/v1/jobs/{job.id}/score",
        json={"person_id": person.id},
    )
    assert response.status_code == 200
    assert response.json()["fit_score"] is not None


def test_approve_job_creates_application(client, db_session) -> None:
    """Approving a job bootstraps an application in pending_approval."""
    _seed_policy(db_session)
    person = _seed_person(db_session)
    job = Job(
        url="https://example.com/approve",
        url_hash=hash_job_url("https://example.com/approve"),
        title="Engineer",
        company="Co",
        source="test",
        status=JobStatus.NEW,
        fit_score=0.8,
    )
    db_session.add(job)
    db_session.commit()

    response = client.patch(
        f"/api/v1/jobs/{job.id}/status",
        json={"action": "approve", "person_id": person.id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"

    from sqlalchemy import select

    app = db_session.scalar(
        select(Application).where(
            Application.person_id == person.id,
            Application.job_id == job.id,
        )
    )
    assert app is not None
    assert app.status == ApplicationStatus.PENDING_APPROVAL


def test_skip_job_endpoint(client, db_session) -> None:
    """PATCH skip moves job to rejected bucket."""
    job = Job(
        url="https://example.com/skip",
        url_hash=hash_job_url("https://example.com/skip"),
        title="Skip Me",
        company="Co",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    response = client.patch(
        f"/api/v1/jobs/{job.id}/status",
        json={"action": "skip"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_queue_endpoint(client, db_session) -> None:
    """GET /jobs/queue returns kanban structure."""
    job = Job(
        url="https://example.com/queue",
        url_hash=hash_job_url("https://example.com/queue"),
        title="Queue Job",
        company="Co",
        source="test",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    response = client.get("/api/v1/jobs/queue")
    assert response.status_code == 200
    data = response.json()
    assert "to_review" in data
    assert data["to_review"]["count"] >= 1


def test_filter_blocks_ingest(db_session) -> None:
    """Hard-filtered jobs are not persisted."""
    _seed_policy(
        db_session,
        blocked_companies_json=json.dumps(["BlockedInc"]),
    )
    raw = RawJob(
        url="https://blocked.com/job",
        title="Dev",
        company="BlockedInc",
        source="test",
    )
    result = ingest_raw_job(db_session, raw)
    assert result.filtered is True
    assert result.job is None
