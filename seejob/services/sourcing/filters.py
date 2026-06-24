"""Deterministic hard filters — no LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass

from seejob.schemas.policy import JobFilters
from seejob.services.sourcing.base import RawJob


@dataclass
class FilterResult:
    """Outcome of applying hard filters to a raw job."""

    passed: bool
    reason: str | None = None


def _normalize(text: str) -> str:
    return text.lower().strip()


def _text_blob(job: RawJob) -> str:
    parts = [job.title, job.company, job.location or "", job.jd_text or ""]
    return _normalize(" ".join(parts))


def apply_hard_filters(
    job: RawJob,
    *,
    job_filters: JobFilters | None,
    blocked_companies: list[str],
    blocked_keywords: list[str],
) -> FilterResult:
    """Apply policy hard filters. Returns passed=False with reason when blocked."""
    blob = _text_blob(job)
    company_norm = _normalize(job.company)

    for blocked in blocked_companies:
        if blocked and _normalize(blocked) in company_norm:
            return FilterResult(False, f"blocked company: {blocked}")

    for keyword in blocked_keywords:
        if keyword and _normalize(keyword) in blob:
            return FilterResult(False, f"blocked keyword: {keyword}")

    if job_filters is None:
        job_filters = JobFilters()

    if job_filters.remote_only and not job.is_remote:
        if "remote" not in blob:
            return FilterResult(False, "remote_only policy — not remote")

    if job_filters.locations:
        if not job.location:
            return FilterResult(False, "location required by policy filters")
        loc_norm = _normalize(job.location)
        if not any(_normalize(loc) in loc_norm for loc in job_filters.locations):
            return FilterResult(False, "location not in allowed list")

    title_norm = _normalize(job.title)
    if job_filters.titles_include:
        if not any(_normalize(t) in title_norm for t in job_filters.titles_include):
            return FilterResult(False, "title missing required include keyword")

    for excluded in job_filters.titles_exclude:
        if excluded and _normalize(excluded) in title_norm:
            return FilterResult(False, f"title excluded: {excluded}")

    for seniority in job_filters.seniority_exclude:
        if seniority and re.search(rf"\b{re.escape(seniority.lower())}\b", title_norm):
            return FilterResult(False, f"seniority excluded: {seniority}")

    if job_filters.must_have_skills:
        for skill in job_filters.must_have_skills:
            if skill and _normalize(skill) not in blob:
                return FilterResult(False, f"missing required skill: {skill}")

    return FilterResult(True)
