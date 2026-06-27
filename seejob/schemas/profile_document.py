"""Schemas for profile supporting documents."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProfileDocumentRead(BaseModel):
    """Uploaded supporting document metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    label: str | None
    filename: str
    path: str
    uploaded_at: datetime


class ProfileDocumentUploadResult(BaseModel):
    """Result of uploading a supporting document."""

    document: ProfileDocumentRead
    chunks_stored: int
    raw_text_length: int


class ProfileDocumentCreate(BaseModel):
    """Optional label when uploading a document."""

    label: str | None = Field(default=None, max_length=255)
