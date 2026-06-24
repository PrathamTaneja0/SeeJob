"""Policy configuration endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from seejob.core.dependencies import get_session
from seejob.schemas.policy import PolicyConfigRead, PolicyConfigUpdate
from seejob.services import policy as policy_service

router = APIRouter()


@router.get("", response_model=PolicyConfigRead)
def get_policy(db: Session = Depends(get_session)) -> PolicyConfigRead:
    """Return current automation policy (rate limits, approval gates, filters)."""
    return policy_service.get_or_create_policy(db)


@router.patch("", response_model=PolicyConfigRead)
def update_policy(
    data: PolicyConfigUpdate,
    db: Session = Depends(get_session),
) -> PolicyConfigRead:
    """Update automation policy settings."""
    return policy_service.update_policy(db, data)
