"""Screening Q&A bank — cache lookup, template seeding, RAG+LLM generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.agents.answer_generator import AnswerGenerator
from seejob.core.llm import resolve_answer_generator
from seejob.models.screening import ScreeningAnswer
from seejob.services.memory import VectorMemoryStore
from seejob.services.profile import get_person
from seejob.services.screening import hash_question

logger = logging.getLogger(__name__)

BEHAVIORAL_TEMPLATES: list[tuple[str, str]] = [
    (
        "Tell me about a time you faced a challenging technical problem.",
        "Describe a specific technical challenge, your approach, and the measurable outcome. "
        "Use STAR format with real project details from your experience.",
    ),
    (
        "Describe a situation where you had to work with a difficult teammate.",
        "Focus on communication, empathy, and how you kept the project on track while "
        "maintaining professionalism.",
    ),
    (
        "Give an example of when you took initiative beyond your assigned responsibilities.",
        "Highlight a concrete situation where you identified a gap and acted without being asked.",
    ),
    (
        "Tell me about a time you failed and what you learned.",
        "Be honest about a setback, what went wrong, and specific changes you made afterward.",
    ),
    (
        "Why are you interested in this role and company?",
        "Connect your skills and career goals to the role requirements. Avoid generic praise.",
    ),
    (
        "Describe your greatest professional achievement.",
        "Quantify impact where possible and tie the achievement to skills relevant to the target role.",
    ),
]


@dataclass
class QAResult:
    """Result of a screening answer lookup or generation."""

    question: str
    answer: str
    from_cache: bool
    source: str
    times_used: int = 0


def seed_behavioral_templates(db: Session, person_id: int) -> int:
    """Seed common behavioral question templates for a person. Returns count added."""
    get_person(db, person_id)
    added = 0

    for question, guidance in BEHAVIORAL_TEMPLATES:
        q_hash = hash_question(question)
        existing = db.scalar(
            select(ScreeningAnswer).where(
                ScreeningAnswer.person_id == person_id,
                ScreeningAnswer.question_hash == q_hash,
            )
        )
        if existing:
            continue
        db.add(
            ScreeningAnswer(
                person_id=person_id,
                question_text=question,
                question_hash=q_hash,
                answer_text=guidance,
                source="template",
                times_used=0,
            )
        )
        added += 1

    db.commit()
    return added


def _get_cached_answer(db: Session, person_id: int, question: str) -> ScreeningAnswer | None:
    q_hash = hash_question(question)
    return db.scalar(
        select(ScreeningAnswer).where(
            ScreeningAnswer.person_id == person_id,
            ScreeningAnswer.question_hash == q_hash,
        )
    )


async def get_or_generate_answer(
    db: Session,
    question: str,
    person_id: int,
    *,
    memory_store: VectorMemoryStore | None = None,
    answer_generator: AnswerGenerator | None = None,
    top_k: int = 5,
) -> QAResult:
    """Return cached answer or generate via RAG+LLM and store."""
    get_person(db, person_id)

    cached = _get_cached_answer(db, person_id, question)
    if cached and cached.source != "template":
        cached.times_used += 1
        db.commit()
        return QAResult(
            question=question,
            answer=cached.answer_text,
            from_cache=True,
            source=cached.source or "cache",
            times_used=cached.times_used,
        )

    store = memory_store or VectorMemoryStore()
    chunks = store.retrieve_relevant(person_id, question, top_k=top_k)
    context = "\n\n---\n\n".join(c.text for c in chunks) if chunks else ""

    if not context:
        person = get_person(db, person_id)
        context_parts = [person.summary or "", person.headline or ""]
        for exp in person.experiences:
            context_parts.append(f"{exp.title} at {exp.company}: {exp.description or ''}")
        context = "\n".join(p for p in context_parts if p)

    generator = resolve_answer_generator(answer_generator)
    answer = await generator.generate(question, context)
    source = "rag+llm"

    q_hash = hash_question(question)
    if cached:
        cached.answer_text = answer
        cached.source = source
        cached.times_used += 1
        db.commit()
        record = cached
    else:
        record = ScreeningAnswer(
            person_id=person_id,
            question_text=question,
            question_hash=q_hash,
            answer_text=answer,
            source=source,
            times_used=1,
        )
        db.add(record)
        db.commit()

    return QAResult(
        question=question,
        answer=answer,
        from_cache=False,
        source=source,
        times_used=record.times_used,
    )
