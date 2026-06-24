"""Security and truthfulness hardening tests for Phase 1 ingestion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from seejob.agents.answer_generator import ANSWER_SYSTEM_PROMPT, OpenAIAnswerGenerator
from seejob.agents.profile_extractor import (
    ExtractedExperience,
    ExtractedProfile,
    ExtractedSkill,
    MockProfileExtractor,
)
from seejob.core.config import Settings, get_settings
from seejob.core.exceptions import LLMUnavailableError, UnsupportedMediaTypeError, URLValidationError
from seejob.core.llm import resolve_answer_generator, resolve_profile_extractor
from seejob.core.url_safety import validate_fetch_url
from seejob.models.person import Person
from seejob.services.ingestion import (
    ground_extracted_profile,
    import_profile_links,
    ingest_text,
    parse_upload,
)
from seejob.services.memory import HashEmbedder, VectorMemoryStore
from seejob.services.qa import get_or_generate_answer

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_CV = (FIXTURES / "sample_cv.txt").read_text(encoding="utf-8")


@pytest.fixture
def clear_settings_cache(monkeypatch):
    monkeypatch.delenv("SEEJOB_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


@pytest.fixture
def mock_extractor() -> MockProfileExtractor:
    return MockProfileExtractor(
        ExtractedProfile(
            full_name="Jane Doe",
            email="jane.doe@example.com",
            experiences=[
                ExtractedExperience(
                    company="Acme Corp",
                    title="Software Engineer",
                    start_date="2020-01-01",
                    is_current=True,
                )
            ],
            skills=[ExtractedSkill(name="Python")],
        )
    )


def test_resolve_profile_extractor_requires_api_key(clear_settings_cache) -> None:
    with pytest.raises(LLMUnavailableError, match="SEEJOB_OPENAI_API_KEY"):
        resolve_profile_extractor()


def test_resolve_profile_extractor_allows_dev_mock(monkeypatch) -> None:
    monkeypatch.delenv("SEEJOB_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "true")
    get_settings.cache_clear()
    extractor = resolve_profile_extractor()
    assert extractor.__class__.__name__ == "MockProfileExtractor"
    get_settings.cache_clear()


def test_resolve_answer_generator_requires_api_key(clear_settings_cache) -> None:
    with pytest.raises(LLMUnavailableError, match="SEEJOB_OPENAI_API_KEY"):
        resolve_answer_generator()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/user",
        "https://evil.com/profile",
        "https://127.0.0.1/user",
        "https://localhost/user",
        "ftp://github.com/user",
    ],
)
def test_validate_fetch_url_blocks_unsafe_urls(url: str) -> None:
    with pytest.raises(URLValidationError):
        validate_fetch_url(url)


def test_validate_fetch_url_allows_github_https() -> None:
    validate_fetch_url("https://github.com/octocat")
    validate_fetch_url("https://api.github.com/users/octocat")
    validate_fetch_url("https://www.linkedin.com/in/janedoe")


@pytest.mark.asyncio
async def test_fetch_url_text_rejects_redirect_to_disallowed_host() -> None:
    request = httpx.Request("GET", "https://github.com/user")
    redirect_response = httpx.Response(
        302,
        request=request,
        headers={"location": "https://evil.com/steal"},
    )
    final_response = httpx.Response(200, request=httpx.Request("GET", "https://evil.com/steal"))

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://github.com/user":
            return redirect_response
        return final_response

    transport = httpx.MockTransport(handler)
    with pytest.raises(URLValidationError, match="not allowed"):
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            response = await client.get("https://github.com/user")
            validate_fetch_url(str(response.url))


def test_parse_upload_rejects_legacy_doc() -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="not supported"):
        parse_upload(b"legacy", "resume.doc")


def test_ground_extracted_profile_strips_ungrounded_entities() -> None:
    source = "Jane Doe worked at Acme Corp as Software Engineer. Skills: Python."
    profile = ExtractedProfile(
        full_name="Jane Doe",
        experiences=[
            ExtractedExperience(
                company="Acme Corp",
                title="Software Engineer",
                start_date="2020-01-01",
            ),
            ExtractedExperience(
                company="Fabricated Inc",
                title="CEO",
                start_date="2019-01-01",
            ),
        ],
        skills=[ExtractedSkill(name="Python"), ExtractedSkill(name="COBOL")],
        project_descriptions=["Software Engineer project at Acme Corp", "Totally fake moon base"],
    )
    grounded = ground_extracted_profile(profile, source)
    assert len(grounded.experiences) == 1
    assert grounded.experiences[0].company == "Acme Corp"
    assert [s.name for s in grounded.skills] == ["Python"]
    assert grounded.project_descriptions == ["Software Engineer project at Acme Corp"]


@pytest.mark.asyncio
async def test_reingest_dedupes_experiences(
    db_session, person, mock_extractor, memory_store
) -> None:
    first = await ingest_text(
        db_session,
        person.id,
        SAMPLE_CV,
        extractor=mock_extractor,
        memory_store=memory_store,
    )
    second = await ingest_text(
        db_session,
        person.id,
        SAMPLE_CV,
        extractor=mock_extractor,
        memory_store=memory_store,
    )
    assert first.experiences_added == 1
    assert second.experiences_added == 0
    db_session.refresh(person)
    assert len(person.experiences) == 1


class _FailingMemoryStore(VectorMemoryStore):
    def add_chunks(self, *args, **kwargs) -> int:
        raise RuntimeError("vector store unavailable")


@pytest.mark.asyncio
async def test_vector_store_failure_rolls_back_sql(
    db_session, person, mock_extractor, memory_store
) -> None:
    failing_store = _FailingMemoryStore(
        persist_dir=memory_store._persist_dir,
        embedder=HashEmbedder(),
    )
    with pytest.raises(RuntimeError, match="vector store unavailable"):
        await ingest_text(
            db_session,
            person.id,
            SAMPLE_CV,
            extractor=mock_extractor,
            memory_store=failing_store,
        )
    db_session.expire_all()
    db_session.refresh(person)
    assert len(person.experiences) == 0
    assert len(person.skills) == 0


@pytest.mark.asyncio
async def test_import_profile_links_blocks_ssrf_url(
    db_session, person, memory_store
) -> None:
    person.linkedin_url = "https://169.254.169.254/latest/meta-data"
    db_session.commit()
    result = await import_profile_links(db_session, person.id, memory_store=memory_store)
    assert result.sources_fetched == []
    assert any("not allowed" in err.lower() or "blocked" in err.lower() for err in result.errors)


def test_upload_rejects_oversized_file(client, person) -> None:
    huge = b"x" * (10 * 1024 * 1024 + 1)
    response = client.post(
        f"/api/v1/profiles/{person.id}/ingest",
        files={"file": ("resume.txt", huge, "text/plain")},
    )
    assert response.status_code == 413


def test_upload_rejects_disallowed_extension(client, person) -> None:
    response = client.post(
        f"/api/v1/profiles/{person.id}/ingest",
        files={"file": ("resume.exe", b"binary", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_upload_rejects_doc_with_415(client, person) -> None:
    response = client.post(
        f"/api/v1/profiles/{person.id}/ingest",
        files={"file": ("resume.doc", b"legacy", "application/msword")},
    )
    assert response.status_code == 415
    assert "docx" in response.json()["detail"].lower()


def test_upload_rejects_mismatched_content_type(client, person) -> None:
    response = client.post(
        f"/api/v1/profiles/{person.id}/ingest",
        files={"file": ("resume.pdf", b"%PDF", "text/plain")},
    )
    assert response.status_code == 415


def test_ingest_without_api_key_returns_503(client, person, clear_settings_cache) -> None:
    response = client.post(
        f"/api/v1/profiles/{person.id}/ingest",
        files={"file": ("resume.txt", SAMPLE_CV.encode(), "text/plain")},
    )
    assert response.status_code == 503
    assert "SEEJOB_OPENAI_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_qa_without_api_key_raises(
    db_session, person, memory_store, clear_settings_cache
) -> None:
    with pytest.raises(LLMUnavailableError):
        await get_or_generate_answer(
            db_session,
            "Why this role?",
            person.id,
            memory_store=memory_store,
        )


@pytest.mark.asyncio
async def test_openai_answer_generator_uses_low_temperature() -> None:
    settings = Settings(openai_api_key="test-key")
    generator = OpenAIAnswerGenerator(settings)
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Answer"}}]}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("seejob.agents.answer_generator.httpx.AsyncClient", return_value=mock_client):
        await generator.generate("Question?", "Context about Acme Corp.")

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["temperature"] == 0.1
    assert "Do NOT invent employers" in payload["messages"][0]["content"]
    assert payload["messages"][0]["content"] == ANSWER_SYSTEM_PROMPT
