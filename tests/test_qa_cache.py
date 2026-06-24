"""Screening Q&A cache hit/miss tests."""

import pytest

from seejob.agents.answer_generator import MockAnswerGenerator
from seejob.models.person import Person
from seejob.models.screening import ScreeningAnswer
from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore
from seejob.services.qa import get_or_generate_answer, seed_behavioral_templates
from seejob.services.screening import hash_question


@pytest.fixture
def memory_store(tmp_path) -> VectorMemoryStore:
    store = VectorMemoryStore(persist_dir=tmp_path / "chroma", embedder=HashEmbedder())
    store.add_chunks(
        1,
        ["Built scalable APIs with FastAPI and reduced latency by 30%."],
        chunk_type=ChunkType.CV,
    )
    return store


@pytest.fixture
def person(db_session) -> Person:
    person = Person(
        full_name="Jane Doe",
        email="jane@example.com",
        work_authorization="citizen",
        summary="Backend engineer specializing in Python.",
    )
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


@pytest.mark.asyncio
async def test_qa_cache_miss_then_hit(db_session, person, memory_store) -> None:
    question = "Describe your experience with FastAPI."
    generator = MockAnswerGenerator()

    first = await get_or_generate_answer(
        db_session,
        question,
        person.id,
        memory_store=memory_store,
        answer_generator=generator,
    )
    assert first.from_cache is False
    assert first.source == "rag+llm"
    assert "FastAPI" in first.answer or "experience" in first.answer.lower()

    second = await get_or_generate_answer(
        db_session,
        question,
        person.id,
        memory_store=memory_store,
        answer_generator=generator,
    )
    assert second.from_cache is True
    assert second.answer == first.answer
    assert second.times_used >= 2


@pytest.mark.asyncio
async def test_qa_hash_deduplication(db_session, person, memory_store) -> None:
    question = "What is your greatest strength?"
    generator = MockAnswerGenerator()

    await get_or_generate_answer(
        db_session,
        question,
        person.id,
        memory_store=memory_store,
        answer_generator=generator,
    )

    q_hash = hash_question(question)
    cached = (
        db_session.query(ScreeningAnswer)
        .filter(
            ScreeningAnswer.person_id == person.id,
            ScreeningAnswer.question_hash == q_hash,
        )
        .one()
    )
    assert cached.times_used >= 1


def test_seed_behavioral_templates_idempotent(db_session, person) -> None:
    first = seed_behavioral_templates(db_session, person.id)
    second = seed_behavioral_templates(db_session, person.id)
    assert first >= 5
    assert second == 0

    count = (
        db_session.query(ScreeningAnswer)
        .filter(ScreeningAnswer.person_id == person.id, ScreeningAnswer.source == "template")
        .count()
    )
    assert count == first
