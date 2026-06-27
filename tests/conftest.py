"""Pytest fixtures for API and database tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from seejob.api.app import create_app
from seejob.core.config import get_settings
from seejob.core.dependencies import get_session
from seejob.models.base import Base


@pytest.fixture(autouse=True)
def force_test_llm_mock(monkeypatch):
    """Use mock LLM in tests unless a test overrides env/key explicitly."""
    monkeypatch.setenv("SEEJOB_ENV", "test")
    monkeypatch.setenv("SEEJOB_ALLOW_MOCK_LLM", "true")
    monkeypatch.setenv("SEEJOB_OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session():
    """In-memory SQLite session for tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """FastAPI test client with overridden DB session."""
    app = create_app()

    def override_get_session():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
