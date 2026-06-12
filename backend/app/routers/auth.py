from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth_services import ProfileConflictError, register_profile
from app.database import get_db
from app.dependencies import get_current_user, get_firebase_identity
from app.firebase_auth import FirebaseIdentity
from app.models import RegisterProfileRequest, UserProfile, UserRead, UserRole


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register-profile", response_model=UserRead)
def post_register_profile(
    payload: RegisterProfileRequest,
    identity: Annotated[FirebaseIdentity, Depends(get_firebase_identity)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    if payload.role == UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin users cannot register publicly",
        )
    try:
        return register_profile(db, identity, payload)
    except ProfileConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/me", response_model=UserRead)
def read_me(current_user: Annotated[UserProfile, Depends(get_current_user)]) -> UserProfile:
    return current_user
