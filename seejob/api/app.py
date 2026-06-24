"""FastAPI application and route registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from seejob import __version__
from seejob.api.routes import applications, events, health, jobs, policy, profiles, site_accounts
from seejob.core.config import get_settings
from seejob.core.database import engine
from seejob.models.base import Base

_DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


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
    app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
    app.include_router(policy.router, prefix="/api/v1/policy", tags=["policy"])
    app.include_router(
        site_accounts.router, prefix="/api/v1/site-accounts", tags=["site-accounts"]
    )

    if _DASHBOARD_DIST.is_dir():
        assets_dir = _DASHBOARD_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="dashboard-assets")

        @app.get("/", include_in_schema=False)
        async def dashboard_index() -> FileResponse:
            return FileResponse(_DASHBOARD_DIST / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def dashboard_spa(full_path: str) -> FileResponse:
            """Serve dashboard SPA; unknown paths fall back to index.html."""
            if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json", "health"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404)
            candidate = _DASHBOARD_DIST / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_DASHBOARD_DIST / "index.html")

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
