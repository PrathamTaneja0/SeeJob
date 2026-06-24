"""FastAPI dependency injection helpers."""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from seejob.core.config import Settings, get_settings
from seejob.core.database import get_db


def get_settings_dep() -> Settings:
    """FastAPI dependency for application settings."""
    return get_settings()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency alias for database sessions."""
    yield from get_db()


SessionDep = Depends(get_session)
SettingsDep = Depends(get_settings_dep)
