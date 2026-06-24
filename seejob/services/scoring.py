"""Semantic job fit scoring via profile memory embeddings."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from seejob.models.job import Job, JobStatus
from seejob.models.policy import PolicyConfig
from seejob.models.person import Person
from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore
from seejob.services.policy import get_policy_config
from seejob.services.profile import get_person

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Outcome of scoring a job against a person profile."""

    fit_score: float
    match_rationale: str
    archived: bool


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _profile_text(person: Person) -> str:
    parts = [
        person.headline or "",
        person.summary or "",
        person.desired_roles or "",
    ]
    for exp in person.experiences:
        parts.append(f"{exp.title} at {exp.company}")
        if exp.description:
            parts.append(exp.description)
    for skill in person.skills:
        parts.append(skill.name)
    return "\n".join(p for p in parts if p.strip())


def _score_with_embeddings(
    jd_text: str,
    person_id: int,
    *,
    memory_store: VectorMemoryStore | None = None,
) -> tuple[float, str]:
    """Score JD against profile chunks using embedding similarity."""
    store = memory_store or VectorMemoryStore(embedder=HashEmbedder())
    chunks = store.retrieve_relevant(
        person_id,
        jd_text[:4000],
        top_k=5,
        chunk_types=[ChunkType.CV, ChunkType.PROJECT, ChunkType.LINKEDIN],
    )

    if chunks:
        embedder = store._embedder  # noqa: SLF001 — test injection point
        jd_vec = embedder.embed([jd_text[:4000]])[0]
        chunk_scores = []
        for chunk in chunks:
            chunk_vec = embedder.embed([chunk.text])[0]
            sim = _cosine_similarity(jd_vec, chunk_vec)
            chunk_scores.append((sim, chunk))

        chunk_scores.sort(key=lambda item: item[0], reverse=True)
        top_sim, top_chunk = chunk_scores[0]
        avg_sim = sum(s for s, _ in chunk_scores) / len(chunk_scores)
        fit = 0.7 * top_sim + 0.3 * avg_sim
        rationale = (
            f"Top memory match ({top_chunk.chunk_type.value}, score={top_sim:.2f}): "
            f"{top_chunk.text[:200]}..."
        )
        return fit, rationale

    return 0.3, "No profile memory chunks found — default low score"


def score_job(
    db: Session,
    job: Job,
    person_id: int,
    *,
    policy: PolicyConfig | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> ScoreResult:
    """Score job fit for a person and update job record."""
    policy = policy or get_policy_config(db)
    person = get_person(db, person_id)

    jd_text = job.jd_text or f"{job.title} at {job.company}"
    if jd_text.strip():
        fit_score, rationale = _score_with_embeddings(
            jd_text,
            person_id,
            memory_store=memory_store,
        )
    else:
        profile_text = _profile_text(person)
        if profile_text.strip():
            embedder = HashEmbedder()
            title_company = f"{job.title} {job.company}"
            vecs = embedder.embed([title_company, profile_text[:2000]])
            fit_score = _cosine_similarity(vecs[0], vecs[1])
            rationale = "Scored from title/company vs profile text (no JD available)"
        else:
            fit_score = 0.0
            rationale = "Insufficient job and profile data for scoring"

    job.fit_score = round(fit_score, 4)
    job.match_rationale = rationale

    threshold = policy.min_fit_score
    if job_filters := policy.job_filters_json:
        from seejob.schemas.policy import PolicyConfigDBFields

        filters = PolicyConfigDBFields.loads_job_filters(job_filters)
        if filters and filters.min_fit_score is not None:
            threshold = filters.min_fit_score

    archived = fit_score < threshold
    if archived and job.status in (JobStatus.NEW, JobStatus.REVIEWED):
        job.status = JobStatus.ARCHIVED

    db.commit()
    db.refresh(job)
    return ScoreResult(fit_score=job.fit_score, match_rationale=rationale, archived=archived)
