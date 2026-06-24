"""Site account credential schemas (passwords masked in responses)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SiteAccountCreate(BaseModel):
    """Create a site account with plaintext credentials (encrypted at rest)."""

    person_id: int
    platform: str = Field(min_length=1, max_length=100)
    domain: str | None = Field(default=None, max_length=255)
    username: str = Field(min_length=1)
    password: str | None = None
    is_active: bool = True


class SiteAccountUpdate(BaseModel):
    """Update site account fields."""

    platform: str | None = Field(default=None, min_length=1, max_length=100)
    domain: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, min_length=1)
    password: str | None = None
    is_active: bool | None = None


class SiteAccountRead(BaseModel):
    """Site account response — password always masked."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    platform: str
    domain: str | None
    username: str
    password_masked: str
    has_session: bool
    is_active: bool
    last_login_at: str | None
    created_at: datetime
    updated_at: datetime
