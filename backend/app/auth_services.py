from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.firebase_auth import (
    FirebaseConfigurationError,
    FirebaseIdentity,
    FirebaseUserManagementError,
    disable_firebase_user,
    enable_firebase_user,
    get_firebase_email_verification_statuses,
)
from app.models import RegisterProfileRequest, UserProfile, UserRole, UserStatus, clean_text, normalize_email


logger = logging.getLogger(__name__)


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


def sync_pending_email_verifications(db: Session, role: UserRole) -> int:
    pending_users = list(
        db.scalars(
            select(UserProfile).where(
                UserProfile.role == role,
                UserProfile.status == UserStatus.pending,
                UserProfile.email_verified.is_(False),
                UserProfile.is_active.is_(True),
                UserProfile.firebase_uid.is_not(None),
            )
        ).all()
    )
    if not pending_users:
        return 0

    try:
        verification_statuses = get_firebase_email_verification_statuses(
            [user.firebase_uid for user in pending_users if user.firebase_uid]
        )
    except (FirebaseConfigurationError, FirebaseUserManagementError):
        logger.warning(
            "Unable to synchronize pending %s email verification statuses from Firebase",
            role.value,
            exc_info=True,
        )
        return 0

    verified_at = utc_now()
    updated_count = 0
    for user in pending_users:
        if not user.firebase_uid or not verification_statuses.get(user.firebase_uid, False):
            continue
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or verified_at
        updated_count += 1

    if updated_count:
        db.commit()
    return updated_count


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
