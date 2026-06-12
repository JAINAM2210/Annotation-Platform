from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth_services import ProfileConflictError, sync_user_from_identity
from app.database import get_db
from app.firebase_auth import FirebaseConfigurationError, FirebaseIdentity, FirebaseTokenError, verify_firebase_token
from app.models import UserProfile, UserRole, UserStatus


bearer_scheme = HTTPBearer(auto_error=True)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_firebase_identity(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> FirebaseIdentity:
    try:
        return verify_firebase_token(credentials.credentials)
    except FirebaseConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except FirebaseTokenError as exc:
        raise unauthorized(str(exc)) from exc


def get_current_user(
    identity: Annotated[FirebaseIdentity, Depends(get_firebase_identity)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    try:
        user = sync_user_from_identity(db, identity)
    except ProfileConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No platform profile is registered for this Firebase user")
    if not user.is_active:
        raise unauthorized("User is inactive or no longer exists")
    return user


def require_approved_user(current_user: Annotated[UserProfile, Depends(get_current_user)]) -> UserProfile:
    if not current_user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email has not been verified")
    if current_user.status != UserStatus.approved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has not been approved")
    return current_user


def require_admin(current_user: Annotated[UserProfile, Depends(require_approved_user)]) -> UserProfile:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges are required")
    return current_user


def require_reviewer_or_admin(current_user: Annotated[UserProfile, Depends(require_approved_user)]) -> UserProfile:
    if current_user.role not in {UserRole.reviewer, UserRole.admin}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer or admin privileges are required")
    return current_user
