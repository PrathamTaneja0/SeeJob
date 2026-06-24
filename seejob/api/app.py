"""FastAPI application and route registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from seejob import __version__
from seejob.api.routes import applications, health, jobs, policy, profiles
from seejob.core.config import get_settings
from seejob.core.database import engine
from seejob.models.base import Base


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks."""
    settings = get_settings()
    settings.ensure_directories()
    if settings.env == "development":
        Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="SeeJob API",
        description=(
            "Autonomous job application system — local-first orchestrator with "
            "approval gates, Q&A caching, and ATS session persistence."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
    app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
    app.include_router(applications.router, prefix="/api/v1/applications", tags=["applications"])
    app.include_router(policy.router, prefix="/api/v1/policy", tags=["policy"])

    return app


app = create_app()


def main() -> None:
    """Run the API server via uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "seejob.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
