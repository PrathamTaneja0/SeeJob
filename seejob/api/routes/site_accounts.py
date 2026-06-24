"""Site account CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.schemas.site_account import SiteAccountCreate, SiteAccountRead, SiteAccountUpdate
from seejob.services.site_account import (
    SiteAccountError,
    create_site_account,
    delete_site_account,
    get_site_account_by_id,
    list_site_accounts,
    update_site_account,
)

router = APIRouter()


@router.get("", response_model=list[SiteAccountRead])
def list_accounts(
    person_id: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> list[SiteAccountRead]:
    """List site accounts with masked passwords."""
    return list_site_accounts(db, person_id=person_id, skip=skip, limit=limit)


@router.get("/{account_id}", response_model=SiteAccountRead)
def get_account(account_id: int, db: Session = Depends(get_session)) -> SiteAccountRead:
    """Get a single site account."""
    try:
        return get_site_account_by_id(db, account_id)
    except SiteAccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=SiteAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(data: SiteAccountCreate, db: Session = Depends(get_session)) -> SiteAccountRead:
    """Create a site account (credentials encrypted at rest)."""
    try:
        return create_site_account(db, data)
    except SiteAccountError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{account_id}", response_model=SiteAccountRead)
def update_account(
    account_id: int,
    data: SiteAccountUpdate,
    db: Session = Depends(get_session),
) -> SiteAccountRead:
    """Update site account fields."""
    try:
        return update_site_account(db, account_id, data)
    except SiteAccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Session = Depends(get_session)) -> None:
    """Delete a site account."""
    try:
        delete_site_account(db, account_id)
    except SiteAccountError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
