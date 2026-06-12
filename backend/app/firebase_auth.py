from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import BACKEND_DIR, get_settings


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str
    email_verified: bool
    name: str | None = None


class FirebaseConfigurationError(RuntimeError):
    pass


class FirebaseTokenError(RuntimeError):
    pass


class FirebaseUserManagementError(RuntimeError):
    pass


def _load_firebase_modules():
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError as exc:  # pragma: no cover - exercised only without dependency installed
        raise FirebaseConfigurationError(
            "firebase-admin is not installed. Add it to the backend environment before using Firebase auth."
        ) from exc
    return firebase_admin, auth, credentials


def _resolve_service_account_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (BACKEND_DIR / candidate).resolve()
    return candidate


@lru_cache
def get_firebase_app():
    settings = get_settings()
    if not settings.firebase_project_id:
        raise FirebaseConfigurationError("FIREBASE_PROJECT_ID is not configured")
    if not settings.firebase_service_account_path:
        raise FirebaseConfigurationError("FIREBASE_SERVICE_ACCOUNT_PATH is not configured")

    firebase_admin, _, credentials = _load_firebase_modules()
    try:
        return firebase_admin.get_app()
    except ValueError:
        service_account_path = _resolve_service_account_path(settings.firebase_service_account_path)
        if not service_account_path.exists():
            raise FirebaseConfigurationError(
                f"Firebase service account file not found at {service_account_path}"
            ) from None
        return firebase_admin.initialize_app(
            credentials.Certificate(str(service_account_path)),
            {"projectId": settings.firebase_project_id},
        )


def verify_firebase_token(token: str) -> FirebaseIdentity:
    if not token.strip():
        raise FirebaseTokenError("Firebase ID token is missing")

    _, auth, _ = _load_firebase_modules()
    try:
        payload = auth.verify_id_token(token, app=get_firebase_app())
    except FirebaseConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - depends on firebase-admin runtime behavior
        raise FirebaseTokenError("Invalid Firebase authentication token") from exc

    uid = str(payload.get("uid") or payload.get("sub") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not uid or not email:
        raise FirebaseTokenError("Firebase token is missing required identity fields")

    return FirebaseIdentity(
        uid=uid,
        email=email,
        email_verified=bool(payload.get("email_verified", False)),
        name=str(payload.get("name") or "").strip() or None,
    )


def disable_firebase_user(firebase_uid: str) -> None:
    if not firebase_uid.strip():
        return

    _, auth, _ = _load_firebase_modules()
    try:
        auth.update_user(firebase_uid, disabled=True, app=get_firebase_app())
    except FirebaseConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - depends on firebase-admin runtime behavior
        raise FirebaseUserManagementError("Failed to disable Firebase user") from exc


def enable_firebase_user(firebase_uid: str) -> None:
    if not firebase_uid.strip():
        return

    _, auth, _ = _load_firebase_modules()
    try:
        auth.update_user(firebase_uid, disabled=False, app=get_firebase_app())
    except FirebaseConfigurationError:
        raise
    except Exception as exc:  # pragma: no cover - depends on firebase-admin runtime behavior
        raise FirebaseUserManagementError("Failed to enable Firebase user") from exc
