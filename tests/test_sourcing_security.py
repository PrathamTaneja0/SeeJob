"""Phase 2 sourcing security and policy hardening tests."""

from __future__ import annotations

import httpx
import pytest

from seejob.core.exceptions import URLValidationError
from seejob.core.url_safety import validate_job_url
from seejob.models.job import Job, JobStatus, hash_job_url
from seejob.models.person import Person, WorkAuthorization
from seejob.services.scoring import score_job
from seejob.services.sourcing.base import RawJob
from seejob.services.sourcing.filters import apply_hard_filters
from seejob.services.sourcing.pipeline import ingest_raw_job
from seejob.services.sourcing.sources.manual import ManualUrlSource

from tests.test_sourcing import SAMPLE_HTML, _seed_person, _seed_policy


@pytest.mark.parametrize(
    "url",
    [
        "http://boards.greenhouse.io/acme/jobs/1",
        "https://127.0.0.1/jobs/1",
        "https://169.254.169.254/latest/meta-data",
        "https://evil.com/jobs/1",
        "ftp://boards.greenhouse.io/job",
    ],
)
def test_validate_job_url_blocks_unsafe_urls(url: str) -> None:
    with pytest.raises(URLValidationError):
        validate_job_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme/jobs/1",
        "https://jobs.lever.co/acme/backend",
        "https://www.linkedin.com/jobs/view/123",
        "https://www.indeed.com/viewjob?jk=abc",
    ],
)
def test_validate_job_url_allows_job_boards(url: str) -> None:
    validate_job_url(url)


def test_validate_job_url_allows_jobs_subdomain() -> None:
    validate_job_url("https://jobs.example.com/opening")


@pytest.mark.asyncio
async def test_manual_url_source_rejects_ssrf() -> None:
    source = ManualUrlSource("https://169.254.169.254/latest/meta-data")
    with pytest.raises(URLValidationError):
        await source.fetch_new_jobs()


@pytest.mark.asyncio
async def test_manual_url_source_rejects_redirect_to_private_ip() -> None:
    request = httpx.Request("GET", "https://boards.greenhouse.io/acme/jobs/1")
    redirect_response = httpx.Response(
        302,
        request=request,
        headers={"location": "https://127.0.0.1/internal"},
    )
    final_response = httpx.Response(200, request=httpx.Request("GET", "https://127.0.0.1/internal"))

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url).startswith("https://boards.greenhouse.io"):
            return redirect_response
        return final_response

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        source = ManualUrlSource("https://boards.greenhouse.io/acme/jobs/1", client=client)
        with pytest.raises(URLValidationError, match="(?i)blocked"):
            await source.fetch_new_jobs()


def test_default_seniority_exclude_when_filters_none() -> None:
    job = RawJob(
        url="https://jobs.example.com/1",
        title="Senior Python Engineer",
        company="Co",
        source="test",
    )
    result = apply_hard_filters(
        job,
        job_filters=None,
        blocked_companies=[],
        blocked_keywords=[],
    )
    assert result.passed is False
    assert "seniority" in (result.reason or "").lower()


def test_create_job_applies_hard_filters(client, db_session) -> None:
    """POST /jobs must not bypass seniority hard filters."""
    _seed_policy(db_session)
    response = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://jobs.example.com/senior-role",
            "title": "Senior Software Engineer",
            "company": "GoodCo",
            "source": "manual",
        },
    )
    assert response.status_code == 422
    assert "seniority" in response.json()["detail"].lower()


def test_create_job_accepts_non_senior_title(client, db_session) -> None:
    _seed_policy(db_session)
    response = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://jobs.example.com/junior-role",
            "title": "Software Engineer",
            "company": "GoodCo",
            "source": "manual",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Software Engineer"


def test_score_reviewed_job_archives_when_below_threshold(db_session, tmp_path) -> None:
    """Re-scoring a reviewed job archives it when fit is below min_fit_score."""
    _seed_policy(db_session, min_fit_score=0.99)
    person = _seed_person(db_session)

    job = Job(
        url="https://jobs.example.com/unrelated",
        url_hash=hash_job_url("https://jobs.example.com/unrelated"),
        title="Java Architect",
        company="LegacyCo",
        jd_text="Enterprise Java and COBOL maintenance.",
        source="test",
        status=JobStatus.REVIEWED,
    )
    db_session.add(job)
    db_session.commit()

    score_job(db_session, job, person.id)
    assert job.status == JobStatus.ARCHIVED


def test_score_endpoint_returns_404_for_missing_person(client, db_session) -> None:
    _seed_policy(db_session)
    job = Job(
        url="https://jobs.example.com/score-me",
        url_hash=hash_job_url("https://jobs.example.com/score-me"),
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
        json={"person_id": 99999},
    )
    assert response.status_code == 404
