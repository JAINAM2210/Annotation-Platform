from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_reviewer_or_admin
from app.models import RejectRequest, UserProfile, UserRead, UserRole, UserStatus


router = APIRouter(prefix="/reviewer", tags=["reviewer"])


@router.get("/signup-requests", response_model=list[UserRead])
def list_signup_requests(
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[UserStatus, Query(alias="status")] = UserStatus.pending,
) -> list[UserProfile]:
    del current_user
    statement = (
        select(UserProfile)
        .where(
            UserProfile.role == UserRole.annotator,
            UserProfile.status == status_filter,
            UserProfile.email_verified.is_(True),
            UserProfile.is_active.is_(True),
        )
        .order_by(UserProfile.created_at.desc(), UserProfile.id.desc())
    )
    return list(db.scalars(statement).all())


@router.post("/signup-requests/{user_id}/approve", response_model=UserRead)
def approve_signup_request(
    user_id: str,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found")
    if user.role != UserRole.annotator:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only annotator requests can be approved here")
    if user.status != UserStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be approved")

    user.status = UserStatus.approved
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by_id = current_user.id
    user.rejection_reason = None
    db.commit()
    db.refresh(user)
    return user


@router.post("/signup-requests/{user_id}/reject", response_model=UserRead)
def reject_signup_request(
    user_id: str,
    payload: RejectRequest,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found")
    if user.role != UserRole.annotator:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only annotator requests can be rejected here")
    if user.status != UserStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be rejected")

    user.status = UserStatus.rejected
    user.approved_at = None
    user.approved_by_id = current_user.id
    user.rejection_reason = payload.reason
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserProfile]:
    del current_user
    statement = select(UserProfile).order_by(UserProfile.created_at.desc(), UserProfile.id.desc())
    return list(db.scalars(statement).all())
