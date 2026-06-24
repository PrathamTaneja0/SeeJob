"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """SeeJob runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEEJOB_",
        extra="ignore",
    )

    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(min_length=16, default="dev-secret-change-me")

    database_url: str = "sqlite:///./seejob.db"

    fernet_key: str = ""

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    documents_dir: Path = Path("./generated/documents")
    browser_profiles_dir: Path = Path("./browser_profiles")

    default_daily_apply_limit: int = 10

    chroma_persist_dir: Path = Path("./chroma_data")
    vector_enabled: bool = False

    openai_api_key: str = ""
    allow_mock_llm: bool = False
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_provider: Literal["sentence_transformers", "openai", "hash"] = "hash"

    sourcing_cron: str = "0 8 * * *"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Accept JSON array or comma-separated CORS origins."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json

                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        """Return True when using SQLite (dev default)."""
        return self.database_url.startswith("sqlite")

    def ensure_directories(self) -> None:
        """Create runtime directories if they do not exist."""
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profiles_dir.mkdir(parents=True, exist_ok=True)
        if self.vector_enabled:
            self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
