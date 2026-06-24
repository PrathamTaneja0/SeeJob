"""Tests for profile Pydantic schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from seejob.models.person import WorkAuthorization
from seejob.schemas.profile import (
    EducationCreate,
    ExperienceCreate,
    PersonCreate,
    PersonUpdate,
    SkillCreate,
)


class TestPersonCreate:
    """Validate person creation schema."""

    def test_valid_person(self) -> None:
        person = PersonCreate(
            full_name="Jane Doe",
            email="jane@example.com",
            work_authorization=WorkAuthorization.CITIZEN,
        )
        assert person.full_name == "Jane Doe"
        assert person.salary_currency == "USD"

    def test_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            PersonCreate(full_name="Jane", email="not-an-email")

    def test_negative_salary_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersonCreate(full_name="Jane", email="jane@example.com", salary_min=-1)


class TestPersonUpdate:
    """Validate partial update schema."""

    def test_partial_update(self) -> None:
        update = PersonUpdate(headline="Senior Engineer")
        assert update.model_dump(exclude_unset=True) == {"headline": "Senior Engineer"}

    def test_empty_update(self) -> None:
        update = PersonUpdate()
        assert update.model_dump(exclude_unset=True) == {}


class TestExperienceCreate:
    """Validate experience schema."""

    def test_valid_experience(self) -> None:
        exp = ExperienceCreate(
            company="Acme Corp",
            title="Software Engineer",
            start_date=date(2020, 1, 1),
            is_current=True,
        )
        assert exp.is_current is True


class TestEducationCreate:
    """Validate education schema."""

    def test_valid_education(self) -> None:
        edu = EducationCreate(institution="MIT", degree="BS", field_of_study="CS")
        assert edu.institution == "MIT"


class TestSkillCreate:
    """Validate skill schema."""

    def test_valid_skill(self) -> None:
        skill = SkillCreate(name="Python", level="expert", years=5.0)
        assert skill.years == 5.0

    def test_negative_years_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SkillCreate(name="Python", years=-1)
