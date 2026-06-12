from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_approved_user, require_reviewer_or_admin
from app.models import (
    AssignmentCreateRequest,
    AssignmentOptionsResponse,
    AssignmentRead,
    PaperAssignmentHistoryResponse,
    ReviewDecisionRequest,
    ReviewSubmissionDetail,
    ReviewSubmissionSummary,
    SubmitResponse,
    UserProfile,
)
from app.services import workflow_service


router = APIRouter(tags=["workflow"])


@router.get("/assignments", response_model=list[AssignmentRead])
def get_assignments(
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AssignmentRead]:
    return workflow_service.list_assignments(db, current_user)


@router.get("/assignments/options", response_model=AssignmentOptionsResponse)
def get_assignment_options(
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AssignmentOptionsResponse:
    return workflow_service.assignment_options(db, current_user)


@router.get("/assignments/papers/{paper_id}/history", response_model=PaperAssignmentHistoryResponse)
def get_paper_assignment_history(
    paper_id: str,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> PaperAssignmentHistoryResponse:
    return workflow_service.paper_assignment_history(db, paper_id, current_user)


@router.post("/assignments", response_model=AssignmentRead)
def post_assignment(
    payload: AssignmentCreateRequest,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AssignmentRead:
    return workflow_service.create_assignment(db, payload, current_user)


@router.post("/assignments/{assignment_id}/cancel", response_model=AssignmentRead)
def post_cancel_assignment(
    assignment_id: str,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AssignmentRead:
    return workflow_service.cancel_assignment(db, assignment_id, current_user)


@router.post("/assignments/{assignment_id}/submit", response_model=SubmitResponse)
def post_submit_assignment(
    assignment_id: str,
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SubmitResponse:
    return workflow_service.submit_assignment(db, assignment_id, current_user)


@router.get("/review/submissions", response_model=list[ReviewSubmissionSummary])
def get_review_submissions(
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str, Query()] = "submitted",
) -> list[ReviewSubmissionSummary]:
    return workflow_service.list_review_submissions(db, current_user, status)


@router.get("/review/submissions/{submission_id}", response_model=ReviewSubmissionDetail)
def get_review_submission_detail(
    submission_id: str,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewSubmissionDetail:
    return workflow_service.review_submission_detail(db, submission_id, current_user)


@router.post("/review/submissions/{submission_id}/return", response_model=ReviewSubmissionSummary)
def post_return_submission(
    submission_id: str,
    payload: ReviewDecisionRequest,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewSubmissionSummary:
    return workflow_service.return_submission(db, submission_id, payload, current_user)


@router.post("/review/submissions/{submission_id}/approve", response_model=ReviewSubmissionSummary)
def post_approve_submission(
    submission_id: str,
    payload: ReviewDecisionRequest,
    current_user: Annotated[UserProfile, Depends(require_reviewer_or_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewSubmissionSummary:
    return workflow_service.approve_submission(db, submission_id, payload, current_user)


@router.get("/exports/papers/{paper_id}")
def get_final_annotation_export(
    paper_id: str,
    current_user: Annotated[UserProfile, Depends(require_approved_user)],
    db: Annotated[Session, Depends(get_db)],
    format: Annotated[str, Query()] = "csv",
) -> Response:
    result = workflow_service.export_final_annotations(db, paper_id, format, current_user)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
