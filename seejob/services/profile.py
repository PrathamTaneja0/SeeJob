"""Profile CRUD service."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from seejob.models.person import Education, Experience, Person, Skill
from seejob.schemas.profile import (
    EducationCreate,
    ExperienceCreate,
    PersonCreate,
    PersonUpdate,
    SkillCreate,
)


class ProfileNotFoundError(LookupError):
    """Raised when a person profile does not exist."""


class DuplicateEmailError(ValueError):
    """Raised when a profile email is already registered."""


def list_persons(db: Session, *, skip: int = 0, limit: int = 50) -> list[Person]:
    """List person profiles with related entities."""
    stmt = (
        select(Person)
        .options(
            selectinload(Person.experiences),
            selectinload(Person.education),
            selectinload(Person.skills),
        )
        .offset(skip)
        .limit(limit)
        .order_by(Person.id)
    )
    return list(db.scalars(stmt).all())


def get_person(db: Session, person_id: int) -> Person:
    """Fetch a person by ID or raise."""
    person = db.scalar(
        select(Person)
        .where(Person.id == person_id)
        .options(
            selectinload(Person.experiences),
            selectinload(Person.education),
            selectinload(Person.skills),
        )
    )
    if person is None:
        raise ProfileNotFoundError(f"Person {person_id} not found")
    return person


def create_person(db: Session, data: PersonCreate) -> Person:
    """Create a new person profile."""
    person = Person(**data.model_dump())
    db.add(person)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateEmailError(f"Email {data.email} is already registered") from exc
    db.refresh(person)
    return get_person(db, person.id)


def update_person(db: Session, person_id: int, data: PersonUpdate) -> Person:
    """Update an existing person profile."""
    person = get_person(db, person_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        email = data.email or person.email
        raise DuplicateEmailError(f"Email {email} is already registered") from exc
    return get_person(db, person_id)


def delete_person(db: Session, person_id: int) -> None:
    """Delete a person profile."""
    person = get_person(db, person_id)
    db.delete(person)
    db.commit()


def add_experience(db: Session, person_id: int, data: ExperienceCreate) -> Experience:
    """Add experience to a person."""
    get_person(db, person_id)
    experience = Experience(person_id=person_id, **data.model_dump())
    db.add(experience)
    db.commit()
    db.refresh(experience)
    return experience


def add_education(db: Session, person_id: int, data: EducationCreate) -> Education:
    """Add education to a person."""
    get_person(db, person_id)
    education = Education(person_id=person_id, **data.model_dump())
    db.add(education)
    db.commit()
    db.refresh(education)
    return education


def add_skill(db: Session, person_id: int, data: SkillCreate) -> Skill:
    """Add skill to a person."""
    get_person(db, person_id)
    skill = Skill(person_id=person_id, **data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill
