"""Profile and resume entity schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from seejob.models.person import WorkAuthorization


class ExperienceBase(BaseModel):
    """Shared experience fields."""

    company: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    location: str | None = None
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None


class ExperienceCreate(ExperienceBase):
    """Create experience entry."""


class ExperienceRead(ExperienceBase):
    """Experience response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class EducationBase(BaseModel):
    """Shared education fields."""

    institution: str = Field(min_length=1, max_length=255)
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    gpa: str | None = None


class EducationCreate(EducationBase):
    """Create education entry."""


class EducationRead(EducationBase):
    """Education response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class SkillBase(BaseModel):
    """Shared skill fields."""

    name: str = Field(min_length=1, max_length=100)
    level: str | None = None
    years: float | None = Field(default=None, ge=0)


class SkillCreate(SkillBase):
    """Create skill entry."""


class SkillRead(SkillBase):
    """Skill response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PersonBase(BaseModel):
    """Shared person profile fields."""

    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: WorkAuthorization = WorkAuthorization.OTHER
    willing_to_relocate: bool = False
    remote_preference: str | None = None
    desired_roles: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_currency: str = "USD"


class PersonCreate(PersonBase):
    """Create a new person profile."""


class PersonUpdate(BaseModel):
    """Partial update for person profile."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    work_authorization: WorkAuthorization | None = None
    willing_to_relocate: bool | None = None
    remote_preference: str | None = None
    desired_roles: str | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None


class PersonRead(PersonBase):
    """Full person profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    experiences: list[ExperienceRead] = []
    education: list[EducationRead] = []
    skills: list[SkillRead] = []
