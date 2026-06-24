"""Profile CRUD and ingestion endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.schemas.ingestion import (
    IngestionRead,
    LinkImportRead,
    ManualTextImport,
    ScreeningAnswerRead,
    ScreeningQuestionRequest,
)
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
from seejob.services import ingestion as ingestion_service
from seejob.services import profile as profile_service
from seejob.services import qa as qa_service

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
    try:
        return profile_service.create_person(db, data)
    except profile_service.DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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
    except profile_service.DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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


@router.post("/{person_id}/ingest", response_model=IngestionRead)
async def ingest_profile_cv(
    person_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> IngestionRead:
    """Upload and ingest a master CV (PDF, DOCX, or TXT)."""
    try:
        content = await file.read()
        result = await ingestion_service.ingest_cv(
            db,
            person_id,
            content,
            file.filename or "upload.pdf",
        )
        return IngestionRead.model_validate(result, from_attributes=True)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{person_id}/import-links", response_model=LinkImportRead)
async def import_profile_links(
    person_id: int,
    db: Session = Depends(get_session),
) -> LinkImportRead:
    """Fetch public LinkedIn/GitHub profile text into vector memory."""
    try:
        result = await ingestion_service.import_profile_links(db, person_id)
        return LinkImportRead.model_validate(result, from_attributes=True)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{person_id}/import-text", response_model=IngestionRead)
async def import_profile_text(
    person_id: int,
    data: ManualTextImport,
    db: Session = Depends(get_session),
) -> IngestionRead:
    """Manually paste profile text when URL scraping is unavailable."""
    try:
        result = await ingestion_service.ingest_text(db, person_id, data.text)
        return IngestionRead.model_validate(result, from_attributes=True)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{person_id}/screening/answer", response_model=ScreeningAnswerRead)
async def answer_screening_question(
    person_id: int,
    data: ScreeningQuestionRequest,
    db: Session = Depends(get_session),
) -> ScreeningAnswerRead:
    """Get cached or RAG-generated answer for a screening question."""
    try:
        result = await qa_service.get_or_generate_answer(db, data.question, person_id)
        return ScreeningAnswerRead.model_validate(result, from_attributes=True)
    except profile_service.ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
