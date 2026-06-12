from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

EDITED_DIR = DATA_DIR / "relations"

PAPER_INDEX_PATH = DATA_DIR / "paper_index.csv"
SENTENCE_INDEX_PATH = DATA_DIR / "sentence_index.csv"
ENTITY_MENTIONS_PATH = DATA_DIR / "entity_mentions.csv"
RAW_RELATIONS_PATH = DATA_DIR / "relation_candidates.csv"
SCHEMA_RELATIONS_PATH = DATA_DIR / "relations.csv"
CUSTOM_SCHEMA_PREDICATES_PATH = DATA_DIR / "custom_relation_predicates.csv"


def _load_env_file() -> None:
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    database_ssl_mode: str
    database_ssl_root_cert: str
    auth_admin_email: str
    auth_admin_full_name: str
    firebase_project_id: str
    firebase_service_account_path: str


@lru_cache
def get_settings() -> Settings:
    _load_env_file()
    return Settings(
        app_name=os.getenv("APP_NAME", "Annotation Platform"),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'annotation_auth.db'}"),
        database_ssl_mode=os.getenv("DATABASE_SSL_MODE", "").strip(),
        database_ssl_root_cert=os.getenv("DATABASE_SSL_ROOT_CERT", "").strip(),
        auth_admin_email=os.getenv("AUTH_ADMIN_EMAIL", "").strip().lower(),
        auth_admin_full_name=os.getenv("AUTH_ADMIN_FULL_NAME", "Admin").strip() or "Admin",
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID", "").strip(),
        firebase_service_account_path=os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip(),
    )
