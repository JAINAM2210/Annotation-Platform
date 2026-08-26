from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_services import (
    deactivate_user_account,
    reactivate_user_account,
    sync_pending_email_verifications,
)
from app.database import get_db
from app.dependencies import require_admin
from app.firebase_auth import FirebaseConfigurationError, FirebaseUserManagementError
from app.models import RejectRequest, UserProfile, UserRead, UserRole, UserStatus


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/signup-requests", response_model=list[UserRead])
def list_signup_requests(
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[UserStatus, Query(alias="status")] = UserStatus.pending,
    role_filter: Annotated[UserRole, Query(alias="role")] = UserRole.reviewer,
) -> list[UserProfile]:
    del current_user
    if role_filter != UserRole.reviewer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin signup request endpoint manages reviewer requests only",
        )
    if status_filter == UserStatus.pending:
        sync_pending_email_verifications(db, UserRole.reviewer)
    statement = (
        select(UserProfile)
        .where(
            UserProfile.role == UserRole.reviewer,
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
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found")
    if user.role != UserRole.reviewer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only reviewer requests can be approved here")
    if user.status not in {UserStatus.pending, UserStatus.rejected}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending or rejected requests can be approved")

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
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found")
    if user.role != UserRole.reviewer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only reviewer requests can be rejected here")
    if user.status != UserStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be rejected")

    user.status = UserStatus.rejected
    user.approved_at = None
    user.approved_by_id = current_user.id
    user.rejection_reason = payload.reason
    db.commit()
    db.refresh(user)
    return user


@router.post("/signup-requests/{user_id}/reopen", response_model=UserRead)
def reopen_signup_request(
    user_id: str,
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found")
    if user.role != UserRole.reviewer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only reviewer requests can be reopened here")
    if user.status != UserStatus.rejected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only rejected requests can be reopened")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive users must be reactivated before reopening")

    user.status = UserStatus.pending
    user.approved_at = None
    user.approved_by_id = None
    user.rejection_reason = None
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserProfile]:
    del current_user
    statement = select(UserProfile).order_by(UserProfile.created_at.desc(), UserProfile.id.desc())
    return list(db.scalars(statement).all())


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot remove their own account")

    try:
        deactivate_user_account(db, user)
    except (FirebaseConfigurationError, FirebaseUserManagementError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/users/{user_id}/reactivate", response_model=UserRead)
def reactivate_user(
    user_id: str,
    current_user: Annotated[UserProfile, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = db.get(UserProfile, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot reactivate their own account")
    if user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already active")

    try:
        return reactivate_user_account(db, user)
    except (FirebaseConfigurationError, FirebaseUserManagementError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
