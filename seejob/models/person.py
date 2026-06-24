"""Person profile and related resume entities."""

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.application import Application
    from seejob.models.screening import ScreeningAnswer
    from seejob.models.site_account import SiteAccount


class WorkAuthorization(str, enum.Enum):
    """Work authorization status for job targeting."""

    CITIZEN = "citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    WORK_VISA = "work_visa"
    STUDENT_VISA = "student_visa"
    REQUIRES_SPONSORSHIP = "requires_sponsorship"
    OTHER = "other"


class Person(Base, TimestampMixin):
    """Primary identity and job-search preferences."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)

    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))

    work_authorization: Mapped[WorkAuthorization] = mapped_column(
        Enum(WorkAuthorization, name="work_authorization"),
        default=WorkAuthorization.OTHER,
        nullable=False,
    )
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remote_preference: Mapped[str | None] = mapped_column(String(50))
    desired_roles: Mapped[str | None] = mapped_column(Text)
    salary_min: Mapped[int | None] = mapped_column()
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        order_by="Experience.start_date.desc()",
    )
    education: Mapped[list["Education"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        order_by="Education.end_date.desc()",
    )
    skills: Mapped[list["Skill"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )
    screening_answers: Mapped[list["ScreeningAnswer"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )
    site_accounts: Mapped[list["SiteAccount"]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(back_populates="person")


class Experience(Base, TimestampMixin):
    """Professional experience entry."""

    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    person: Mapped["Person"] = relationship(back_populates="experiences")


class Education(Base, TimestampMixin):
    """Education entry."""

    __tablename__ = "education"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(255))
    field_of_study: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    gpa: Mapped[str | None] = mapped_column(String(20))

    person: Mapped["Person"] = relationship(back_populates="education")


class Skill(Base, TimestampMixin):
    """Skill with optional proficiency level."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str | None] = mapped_column(String(50))
    years: Mapped[float | None] = mapped_column()

    person: Mapped["Person"] = relationship(back_populates="skills")
