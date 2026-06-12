from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import BACKEND_DIR, Settings, get_settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _resolve_backend_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    return str(path)


def _engine_kwargs(settings: Settings) -> dict[str, object]:
    database_url = _normalize_database_url(settings.database_url)
    if database_url == "sqlite:///:memory:":
        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}

    connect_args: dict[str, str] = {}
    if settings.database_ssl_mode:
        connect_args["sslmode"] = settings.database_ssl_mode
    if settings.database_ssl_root_cert:
        connect_args["sslrootcert"] = _resolve_backend_path(settings.database_ssl_root_cert)
    return {"connect_args": connect_args} if connect_args else {}


settings = get_settings()
engine = create_engine(_normalize_database_url(settings.database_url), future=True, **_engine_kwargs(settings))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _user_profile_migrations() -> dict[str, str]:
    if engine.dialect.name == "postgresql":
        return {
            "designation": "ALTER TABLE user_profiles ADD COLUMN designation TEXT",
            "institute": "ALTER TABLE user_profiles ADD COLUMN institute TEXT",
            "state": "ALTER TABLE user_profiles ADD COLUMN state TEXT",
            "country": "ALTER TABLE user_profiles ADD COLUMN country TEXT",
            "email_verified": "ALTER TABLE user_profiles ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE",
            "email_verified_at": "ALTER TABLE user_profiles ADD COLUMN email_verified_at TIMESTAMPTZ",
        }
    return {
        "designation": "ALTER TABLE user_profiles ADD COLUMN designation TEXT",
        "institute": "ALTER TABLE user_profiles ADD COLUMN institute TEXT",
        "state": "ALTER TABLE user_profiles ADD COLUMN state TEXT",
        "country": "ALTER TABLE user_profiles ADD COLUMN country TEXT",
        "email_verified": "ALTER TABLE user_profiles ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0",
        "email_verified_at": "ALTER TABLE user_profiles ADD COLUMN email_verified_at DATETIME",
    }


def _migrate_user_profiles_table() -> None:
    inspector = inspect(engine)
    if "user_profiles" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("user_profiles")}
    migrations = _user_profile_migrations()

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_profiles_firebase_uid ON user_profiles (firebase_uid)"))


def create_database() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_user_profiles_table()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
