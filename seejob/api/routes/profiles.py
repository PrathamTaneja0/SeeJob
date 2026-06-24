"""Profile CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.schemas.profile import (
    EducationCreate,
    EducationRead,
    ExperienceCreate,
    ExperienceRead,
    PersonCreate,
    PersonRead,
    PersonUpdate,
    SkillCreate,
    SkillRead,
)
from seejob.services import profile as profile_service

router = APIRouter()


@router.get("", response_model=list[PersonRead])
def list_profiles(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_session),
) -> list[PersonRead]:
    """List all person profiles."""
    return profile_service.list_persons(db, skip=skip, limit=limit)


@router.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_profile(data: PersonCreate, db: Session = Depends(get_session)) -> PersonRead:
    """Create a new person profile."""
    return profile_service.create_person(db, data)


@router.get("/{person_id}", response_model=PersonRead)
def get_profile(person_id: int, db: Session = Depends(get_session)) -> PersonRead:
    """Get a person profile by ID."""
    try:
        return profile_service.get_person(db, person_id)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{person_id}", response_model=PersonRead)
def update_profile(
    person_id: int,
    data: PersonUpdate,
    db: Session = Depends(get_session),
) -> PersonRead:
    """Update a person profile."""
    try:
        return profile_service.update_person(db, person_id, data)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(person_id: int, db: Session = Depends(get_session)) -> None:
    """Delete a person profile."""
    try:
        profile_service.delete_person(db, person_id)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{person_id}/experiences",
    response_model=ExperienceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_experience(
    person_id: int,
    data: ExperienceCreate,
    db: Session = Depends(get_session),
) -> ExperienceRead:
    """Add an experience entry to a profile."""
    try:
        return profile_service.add_experience(db, person_id, data)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{person_id}/education",
    response_model=EducationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_education(
    person_id: int,
    data: EducationCreate,
    db: Session = Depends(get_session),
) -> EducationRead:
    """Add an education entry to a profile."""
    try:
        return profile_service.add_education(db, person_id, data)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{person_id}/skills",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
)
def add_skill(
    person_id: int,
    data: SkillCreate,
    db: Session = Depends(get_session),
) -> SkillRead:
    """Add a skill to a profile."""
    try:
        return profile_service.add_skill(db, person_id, data)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
