from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Date, DateTime, create_engine, inspect, text
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


def _migrate_assignment_due_date() -> None:
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    if "annotation_assignments" not in inspector.get_table_names():
        return
    due_column = next((column for column in inspector.get_columns("annotation_assignments") if column["name"] == "due_at"), None)
    if due_column is None:
        return
    due_type = due_column["type"]
    if isinstance(due_type, Date) and not isinstance(due_type, DateTime):
        return

    with engine.begin() as connection:
        connection.execute(text(
            """
            ALTER TABLE annotation_assignments
            ALTER COLUMN due_at TYPE DATE
            USING (due_at AT TIME ZONE 'UTC')::date
            """
        ))


def _migrate_annotation_revision_workflow() -> None:
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "annotation_submissions" not in table_names or "annotation_submission_relations" not in table_names:
        return

    submission_columns = {column["name"] for column in inspector.get_columns("annotation_submissions")}
    relation_columns = {column["name"] for column in inspector.get_columns("annotation_submission_relations")}
    with engine.begin() as connection:
        if "parent_submission_id" not in submission_columns:
            connection.execute(text("ALTER TABLE annotation_submissions ADD COLUMN parent_submission_id UUID"))
        if "created_by_id" not in submission_columns:
            connection.execute(text("ALTER TABLE annotation_submissions ADD COLUMN created_by_id UUID"))
        if "editor_role" not in submission_columns:
            connection.execute(text("ALTER TABLE annotation_submissions ADD COLUMN editor_role TEXT"))

        connection.execute(text(
            """
            UPDATE annotation_submissions sub
            SET created_by_id = aa.annotator_id,
                editor_role = 'annotator'
            FROM annotation_assignments aa
            WHERE aa.id = sub.assignment_id
              AND (sub.created_by_id IS NULL OR sub.editor_role IS NULL)
            """
        ))
        connection.execute(text(
            """
            WITH ordered AS (
                SELECT id,
                       LAG(id) OVER (PARTITION BY assignment_id ORDER BY version, created_at, id) AS previous_id
                FROM annotation_submissions
            )
            UPDATE annotation_submissions sub
            SET parent_submission_id = ordered.previous_id
            FROM ordered
            WHERE ordered.id = sub.id
              AND sub.parent_submission_id IS NULL
              AND ordered.previous_id IS NOT NULL
            """
        ))
        connection.execute(text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint constraint_row
                    JOIN pg_attribute attribute_row
                      ON attribute_row.attrelid = constraint_row.conrelid
                     AND attribute_row.attnum = ANY(constraint_row.conkey)
                    WHERE constraint_row.contype = 'f'
                      AND constraint_row.conrelid = 'annotation_submissions'::regclass
                      AND attribute_row.attname = 'parent_submission_id'
                ) THEN
                    ALTER TABLE annotation_submissions
                    ADD CONSTRAINT fk_annotation_submission_parent
                    FOREIGN KEY (parent_submission_id) REFERENCES annotation_submissions(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint constraint_row
                    JOIN pg_attribute attribute_row
                      ON attribute_row.attrelid = constraint_row.conrelid
                     AND attribute_row.attnum = ANY(constraint_row.conkey)
                    WHERE constraint_row.contype = 'f'
                      AND constraint_row.conrelid = 'annotation_submissions'::regclass
                      AND attribute_row.attname = 'created_by_id'
                ) THEN
                    ALTER TABLE annotation_submissions
                    ADD CONSTRAINT fk_annotation_submission_creator
                    FOREIGN KEY (created_by_id) REFERENCES user_profiles(id) ON DELETE SET NULL;
                END IF;
            END $$
            """
        ))

        if "raw_payload" not in relation_columns:
            connection.execute(text("ALTER TABLE annotation_submission_relations ADD COLUMN raw_payload JSONB"))
        if "logical_relation_id" not in relation_columns:
            connection.execute(text("ALTER TABLE annotation_submission_relations ADD COLUMN logical_relation_id UUID"))
        connection.execute(text(
            """
            UPDATE annotation_submission_relations
            SET logical_relation_id = (
                substr(md5(COALESCE(raw_payload->>'logical_relation_id', raw_payload->>'relation_id', id::text)), 1, 8) || '-' ||
                substr(md5(COALESCE(raw_payload->>'logical_relation_id', raw_payload->>'relation_id', id::text)), 9, 4) || '-' ||
                substr(md5(COALESCE(raw_payload->>'logical_relation_id', raw_payload->>'relation_id', id::text)), 13, 4) || '-' ||
                substr(md5(COALESCE(raw_payload->>'logical_relation_id', raw_payload->>'relation_id', id::text)), 17, 4) || '-' ||
                substr(md5(COALESCE(raw_payload->>'logical_relation_id', raw_payload->>'relation_id', id::text)), 21, 12)
            )::uuid
            WHERE logical_relation_id IS NULL
            """
        ))
        connection.execute(text("ALTER TABLE annotation_submission_relations ALTER COLUMN logical_relation_id SET NOT NULL"))
        connection.execute(text("ALTER TABLE annotation_submission_relations ALTER COLUMN logical_relation_id SET DEFAULT gen_random_uuid()"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_submission_logical_relation "
            "ON annotation_submission_relations (submission_id, logical_relation_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_annotation_submissions_parent_submission_id "
            "ON annotation_submissions (parent_submission_id)"
        ))


def create_database() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_user_profiles_table()
    _migrate_assignment_due_date()
    _migrate_annotation_revision_workflow()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
