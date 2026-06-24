"""Ingestion and import response schemas."""

from pydantic import BaseModel, Field


class IngestionRead(BaseModel):
    """Result of CV ingestion."""

    person_id: int
    raw_text_length: int
    chunks_stored: int
    experiences_added: int
    education_added: int
    skills_added: int
    fields_updated: list[str]
    project_chunks: int
    behavioral_chunks: int


class LinkImportRead(BaseModel):
    """Result of LinkedIn/GitHub link import."""

    person_id: int
    sources_fetched: list[str]
    chunks_stored: int
    errors: list[str]


class ManualTextImport(BaseModel):
    """Manual text paste for profile enrichment."""

    text: str = Field(min_length=1)


class ScreeningAnswerRead(BaseModel):
    """Screening answer lookup or generation result."""

    question: str
    answer: str
    from_cache: bool
    source: str
    times_used: int


class ScreeningQuestionRequest(BaseModel):
    """Request body for generating a screening answer."""

    question: str = Field(min_length=1)
