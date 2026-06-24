"""Profile ingestion tests with mocked LLM."""

from datetime import date
from pathlib import Path

import pytest

from seejob.agents.profile_extractor import (
    ExtractedEducation,
    ExtractedExperience,
    ExtractedProfile,
    ExtractedSkill,
    MockProfileExtractor,
)
from seejob.models.person import Person
from seejob.services.ingestion import chunk_text, ingest_cv, ingest_text, parse_upload
from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CV = (FIXTURES / "sample_cv.txt").read_text(encoding="utf-8")


@pytest.fixture
def mock_extractor() -> MockProfileExtractor:
    return MockProfileExtractor(
        ExtractedProfile(
            full_name="Jane Doe",
            email="jane.doe@example.com",
            location="San Francisco, CA",
            summary="Backend engineer with 5 years experience.",
            experiences=[
                ExtractedExperience(
                    company="Acme Corp",
                    title="Software Engineer",
                    start_date="2020-01-01",
                    is_current=True,
                    description="Built REST APIs with FastAPI.",
                )
            ],
            education=[
                ExtractedEducation(
                    institution="State University",
                    degree="B.S. Computer Science",
                    end_date="2020-05-01",
                )
            ],
            skills=[ExtractedSkill(name="Python"), ExtractedSkill(name="FastAPI")],
            project_descriptions=["Job Tracker: SQLite and React application tracker."],
            behavioral_stories=["Led incident response reducing downtime by 40%."],
        )
    )


@pytest.fixture
def memory_store(tmp_path) -> VectorMemoryStore:
    return VectorMemoryStore(persist_dir=tmp_path / "chroma", embedder=HashEmbedder())


@pytest.fixture
def person(db_session) -> Person:
    person = Person(
        full_name="Jane Doe",
        email="jane@example.com",
        work_authorization="citizen",
    )
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


def test_parse_upload_txt() -> None:
    text = parse_upload(SAMPLE_CV.encode(), "resume.txt")
    assert "Jane Doe" in text
    assert "Acme Corp" in text


def test_chunk_text_overlap() -> None:
    text = "word " * 500
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


@pytest.mark.asyncio
async def test_ingest_text_creates_entities(
    db_session, person, mock_extractor, memory_store
) -> None:
    result = await ingest_text(
        db_session,
        person.id,
        SAMPLE_CV,
        extractor=mock_extractor,
        memory_store=memory_store,
    )

    assert result.person_id == person.id
    assert result.raw_text_length > 0
    assert result.chunks_stored > 0
    assert result.experiences_added == 1
    assert result.education_added == 1
    assert result.skills_added == 2
    assert len(result.fields_updated) > 0

    db_session.refresh(person)
    assert len(person.experiences) == 1
    assert person.experiences[0].company == "Acme Corp"
    assert person.experiences[0].start_date == date(2020, 1, 1)
    assert len(person.skills) == 2


@pytest.mark.asyncio
async def test_ingest_cv_file(
    db_session, person, mock_extractor, memory_store
) -> None:
    result = await ingest_cv(
        db_session,
        person.id,
        SAMPLE_CV.encode(),
        "resume.txt",
        extractor=mock_extractor,
        memory_store=memory_store,
    )
    assert result.chunks_stored >= 1


@pytest.mark.asyncio
async def test_ingest_seeds_behavioral_templates(
    db_session, person, mock_extractor, memory_store
) -> None:
    await ingest_text(
        db_session,
        person.id,
        SAMPLE_CV,
        extractor=mock_extractor,
        memory_store=memory_store,
    )
    from seejob.models.screening import ScreeningAnswer

    templates = (
        db_session.query(ScreeningAnswer)
        .filter(ScreeningAnswer.person_id == person.id, ScreeningAnswer.source == "template")
        .all()
    )
    assert len(templates) >= 5
