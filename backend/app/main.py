from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.data_errors import DataServiceError, data_http_exception
from app.database import create_database, get_db
from app.dependencies import require_approved_user, require_reviewer_or_admin
from app.models import (
    AddRelationPayload,
    CustomPredicatePayload,
    DatasetInfo,
    PaperDetailResponse,
    PaperEditorPayload,
    ParagraphCommentsPayload,
    PaperSummary,
    RelationRecord,
    UserProfile,
)
from app.routers import admin, auth, reviewer, workflow
from app.services import db_editor_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    create_database()
    yield


app = FastAPI(title="Annotation Platform API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(reviewer.router)
app.include_router(workflow.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/datasets", response_model=list[DatasetInfo])
def get_datasets(current_user: Annotated[UserProfile, Depends(require_approved_user)]) -> list[DatasetInfo]:
    del current_user
    return db_editor_service.list_datasets()


@app.get("/schema/predicates", response_model=list[str])
def get_schema_predicates(
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[str]:
    del current_user
    try:
        return db_editor_service.list_schema_predicates(db)
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc


@app.get("/schema/predicates/direct", response_model=list[str])
def get_direct_schema_predicates(
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[str]:
    del current_user
    try:
        return db_editor_service.list_schema_predicates(db, direct_only=True)
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc


@app.post("/schema/predicates/direct", response_model=list[str])
def post_direct_schema_predicate(
    payload: CustomPredicatePayload,
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[str]:
    try:
        return db_editor_service.save_custom_schema_predicate(db, payload.predicate, current_user)
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc


@app.get("/papers", response_model=list[PaperSummary])
def get_papers(
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
    dataset: str = "raw",
) -> list[PaperSummary]:
    del dataset
    try:
        return db_editor_service.list_papers(db, current_user)
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc


@app.get("/paper/{paper_id}", response_model=PaperDetailResponse)
def get_paper(
    paper_id: str,
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
    dataset: str = "raw",
) -> PaperDetailResponse:
    del dataset
    try:
        return db_editor_service.paper_detail(db, paper_id, current_user)
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc


@app.post("/paper/{paper_id}/relations/save")
def post_save_relations(
    paper_id: str,
    payload: PaperEditorPayload,
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if payload.paper_id != paper_id:
        raise HTTPException(status_code=400, detail="paper_id mismatch")
    try:
        saved_to = db_editor_service.save_relations(
            db,
            paper_id,
            payload.relations,
            payload.paragraph_comments,
            payload.editor_mode,
            current_user,
            payload.base_submission_id,
        )
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc
    return {"saved_to": saved_to}


@app.post("/paper/{paper_id}/paragraph-comments/save")
def post_save_paragraph_comments(
    paper_id: str,
    payload: ParagraphCommentsPayload,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if payload.paper_id != paper_id:
        raise HTTPException(status_code=400, detail="paper_id mismatch")
    try:
        saved_to = db_editor_service.save_reviewer_paragraph_comments(
            db,
            paper_id,
            payload.paragraph_comments,
            current_user,
        )
    except DataServiceError as exc:
        raise data_http_exception(exc) from exc
    return {"saved_to": saved_to}


@app.post("/paper/{paper_id}/relations/add", response_model=RelationRecord)
def post_add_relation(paper_id: str, payload: AddRelationPayload, current_user: Annotated[UserProfile, Depends(require_approved_user)]) -> RelationRecord:
    del current_user
    if payload.paper_id != paper_id:
        raise HTTPException(status_code=400, detail="paper_id mismatch")
    return payload.relation
