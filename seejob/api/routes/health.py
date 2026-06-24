"""Health check endpoint."""

from fastapi import APIRouter

from seejob import __version__
from seejob.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str | bool]:
    """Return service health and version."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.env,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
    }
