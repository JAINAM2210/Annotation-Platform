from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.firebase_auth import FirebaseIdentity, disable_firebase_user, enable_firebase_user
from app.models import RegisterProfileRequest, UserProfile, UserRole, UserStatus, clean_text, normalize_email


class ProfileConflictError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_user_by_email(db: Session, email: str) -> UserProfile | None:
    normalized = normalize_email(email)
    return db.scalar(select(UserProfile).where(func.lower(UserProfile.email) == normalized))


def get_user_by_firebase_uid(db: Session, firebase_uid: str) -> UserProfile | None:
    return db.scalar(select(UserProfile).where(UserProfile.firebase_uid == firebase_uid))


def admin_exists(db: Session) -> bool:
    return db.scalar(select(UserProfile.id).where(UserProfile.role == UserRole.admin).limit(1)) is not None


def _is_bootstrap_admin_identity(db: Session, identity: FirebaseIdentity) -> bool:
    settings = get_settings()
    if not settings.auth_admin_email:
        return False
    return (
        not admin_exists(db)
        and identity.email_verified
        and normalize_email(identity.email) == settings.auth_admin_email
    )


def _ensure_identity_link(user: UserProfile, identity: FirebaseIdentity) -> None:
    if user.firebase_uid and user.firebase_uid != identity.uid:
        raise ProfileConflictError("This backend profile is already linked to a different Firebase account")
    user.firebase_uid = identity.uid


def _sync_identity_fields(user: UserProfile, identity: FirebaseIdentity, *, full_name: str | None = None) -> None:
    _ensure_identity_link(user, identity)
    user.email = normalize_email(identity.email)
    user.full_name = clean_text(full_name or user.full_name or identity.name or "User")
    user.email_verified = identity.email_verified
    user.email_verified_at = utc_now() if identity.email_verified else None


def _sync_profile_fields(user: UserProfile, payload: RegisterProfileRequest) -> None:
    user.full_name = clean_text(payload.full_name)
    user.designation = clean_text(payload.designation)
    user.institute = clean_text(payload.institute)
    user.state = clean_text(payload.state)
    user.country = clean_text(payload.country)


def _promote_bootstrap_admin(user: UserProfile) -> None:
    settings = get_settings()
    user.email = settings.auth_admin_email
    user.full_name = settings.auth_admin_full_name
    user.role = UserRole.admin
    user.status = UserStatus.approved
    user.is_active = True
    user.email_verified = True
    user.email_verified_at = user.email_verified_at or utc_now()
    user.approved_at = user.approved_at or utc_now()
    user.rejection_reason = None


def register_profile(db: Session, identity: FirebaseIdentity, payload: RegisterProfileRequest) -> UserProfile:
    user = get_user_by_firebase_uid(db, identity.uid) or get_user_by_email(db, identity.email)
    bootstrap_admin = _is_bootstrap_admin_identity(db, identity)

    if user is None:
        user = UserProfile(
            firebase_uid=identity.uid,
            email=normalize_email(identity.email),
            full_name=payload.full_name,
            role=payload.role,
            designation=payload.designation,
            institute=payload.institute,
            state=payload.state,
            country=payload.country,
            status=UserStatus.pending,
            is_active=True,
            email_verified=identity.email_verified,
            email_verified_at=utc_now() if identity.email_verified else None,
        )
        if bootstrap_admin:
            _promote_bootstrap_admin(user)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if user.role != payload.role and not bootstrap_admin:
        raise ProfileConflictError("A backend profile already exists for this email with a different role")

    _sync_identity_fields(user, identity, full_name=payload.full_name)
    _sync_profile_fields(user, payload)
    if bootstrap_admin:
        _promote_bootstrap_admin(user)
    db.commit()
    db.refresh(user)
    return user


def sync_user_from_identity(db: Session, identity: FirebaseIdentity) -> UserProfile | None:
    user = get_user_by_firebase_uid(db, identity.uid) or get_user_by_email(db, identity.email)

    if user is None:
        if not _is_bootstrap_admin_identity(db, identity):
            return None
        user = UserProfile(
            firebase_uid=identity.uid,
            email=normalize_email(identity.email),
            full_name=identity.name or get_settings().auth_admin_full_name,
            role=UserRole.admin,
            designation="",
            institute="",
            state="",
            country="",
            status=UserStatus.approved,
            is_active=True,
            email_verified=True,
            email_verified_at=utc_now(),
            approved_at=utc_now(),
        )
        _promote_bootstrap_admin(user)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    _sync_identity_fields(user, identity)
    if _is_bootstrap_admin_identity(db, identity):
        _promote_bootstrap_admin(user)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user_account(db: Session, user: UserProfile) -> UserProfile:
    if user.firebase_uid:
        disable_firebase_user(user.firebase_uid)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def reactivate_user_account(db: Session, user: UserProfile) -> UserProfile:
    if user.firebase_uid:
        enable_firebase_user(user.firebase_uid)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user
