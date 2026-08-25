from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    AssignmentCreateRequest,
    AssignmentOptionsResponse,
    AssignmentRead,
    PaperAssignmentHistoryResponse,
    PaperAssignmentState,
    PaperSummary,
    ReviewDecisionRequest,
    ReviewSubmissionDetail,
    ReviewSubmissionSummary,
    SubmitResponse,
    UserProfile,
    UserRead,
    UserRole,
    UserStatus,
)
from app.services import db_editor_service


ASSIGNMENT_ACTIVE_STATUSES = ("assigned", "in_progress", "submitted", "review_in_progress", "returned")
ASSIGNMENT_EDITABLE_STATUSES = ("assigned", "in_progress", "returned")
ASSIGNMENT_REVIEW_EDITABLE_STATUSES = ("submitted", "review_in_progress")
ASSIGNMENT_VISIBLE_STATUSES = ("assigned", "in_progress", "submitted", "review_in_progress", "returned", "approved")
SUBMISSION_REVIEW_STATUSES = ("submitted", "returned", "approved")


@dataclass(frozen=True)
class ExportResult:
    content: str
    media_type: str
    filename: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _row_value(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _float_value(value: object, default: float = 1.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _execute(db: Session, statement, params: dict | None = None):
    return db.execute(statement, params or {})


def _json_param(db: Session, value: dict[str, object]) -> str | dict[str, object]:
    if db.get_bind().dialect.name == "postgresql":
        return json.dumps(value)
    return value


def _json_expr(db: Session) -> str:
    return "CAST(:metadata AS JSONB)" if db.get_bind().dialect.name == "postgresql" else ":metadata"


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _paper_row_by_external_id(db: Session, paper_id: str):
    row = _execute(db, text("SELECT id, paper_id, title, doi FROM papers WHERE paper_id = :paper_id"), {"paper_id": paper_id}).mappings().first()
    if row is None:
        raise _not_found("Paper not found")
    return row


def _paper_row_by_uuid(db: Session, paper_uuid: str):
    row = _execute(db, text("SELECT id, paper_id, title, doi FROM papers WHERE id = :paper_uuid"), {"paper_uuid": paper_uuid}).mappings().first()
    if row is None:
        raise _not_found("Paper not found")
    return row


def _latest_submission(db: Session, assignment_id: str, statuses: tuple[str, ...] | None = None):
    if statuses:
        statement = text(
            """
            SELECT id, version, status, parent_submission_id, created_by_id, editor_role, created_at, submitted_at
            FROM annotation_submissions
            WHERE assignment_id = :assignment_id AND status IN :statuses
            ORDER BY version DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ).bindparams(bindparam("statuses", expanding=True))
        return _execute(db, statement, {"assignment_id": assignment_id, "statuses": statuses}).mappings().first()
    return _execute(db, text(
        """
        SELECT id, version, status, parent_submission_id, created_by_id, editor_role, created_at, submitted_at
        FROM annotation_submissions
        WHERE assignment_id = :assignment_id
        ORDER BY version DESC, created_at DESC, id DESC
        LIMIT 1
        """
    ), {"assignment_id": assignment_id}).mappings().first()


def _latest_review_comment(db: Session, assignment_id: str | None) -> str | None:
    if not assignment_id:
        return None
    row = _execute(db, text(
        """
        SELECT decision.comment
        FROM review_decisions decision
        JOIN annotation_submissions sub ON sub.id = decision.submission_id
        WHERE sub.assignment_id = :assignment_id
          AND decision.comment IS NOT NULL
          AND trim(decision.comment) <> ''
        ORDER BY decision.created_at DESC, decision.id DESC
        LIMIT 1
        """
    ), {"assignment_id": assignment_id}).first()
    return _row_value(row[0]) if row else None


def _assignment_base_row(db: Session, assignment_id: str):
    row = _execute(db, text(
        """
        SELECT aa.id, aa.paper_id AS paper_uuid, aa.annotator_id, aa.reviewer_id, aa.status,
               aa.assigned_at, aa.started_at, aa.submitted_at, aa.completed_at, aa.due_at,
               p.paper_id, p.title AS paper_title, p.doi,
               annotator.full_name AS annotator_name, annotator.email AS annotator_email,
               reviewer.full_name AS reviewer_name, reviewer.email AS reviewer_email
        FROM annotation_assignments aa
        JOIN papers p ON p.id = aa.paper_id
        LEFT JOIN user_profiles annotator ON annotator.id = aa.annotator_id
        LEFT JOIN user_profiles reviewer ON reviewer.id = aa.reviewer_id
        WHERE aa.id = :assignment_id
        """
    ), {"assignment_id": assignment_id}).mappings().first()
    if row is None:
        raise _not_found("Assignment not found")
    return row


def _assignment_read_from_row(db: Session, row) -> AssignmentRead:
    latest = _latest_submission(db, _row_value(row["id"]))
    latest_submission_id = _row_value(latest["id"]) if latest else None
    return AssignmentRead(
        id=_row_value(row["id"]),
        paper_id=_row_value(row["paper_id"]),
        paper_title=_row_value(row["paper_title"]),
        doi=_row_value(row["doi"]),
        annotator_id=_row_value(row["annotator_id"]) or None,
        annotator_name=_row_value(row["annotator_name"]),
        annotator_email=_row_value(row["annotator_email"]),
        reviewer_id=_row_value(row["reviewer_id"]) or None,
        reviewer_name=_row_value(row["reviewer_name"]),
        reviewer_email=_row_value(row["reviewer_email"]),
        status=_row_value(row["status"]),
        assigned_at=row["assigned_at"],
        started_at=row["started_at"],
        submitted_at=row["submitted_at"],
        completed_at=row["completed_at"],
        due_at=row["due_at"],
        latest_submission_id=latest_submission_id,
        latest_submission_status=_row_value(latest["status"]) if latest else None,
        latest_submission_version=int(latest["version"] or 0) if latest else None,
        latest_review_comment=_latest_review_comment(db, _row_value(row["id"])),
    )


def assignment_state_from_read(assignment: AssignmentRead | None) -> PaperAssignmentState | None:
    if assignment is None:
        return None
    return PaperAssignmentState(
        assignment_id=assignment.id,
        status=assignment.status,
        annotator_id=assignment.annotator_id,
        reviewer_id=assignment.reviewer_id,
        latest_submission_id=assignment.latest_submission_id,
        latest_submission_status=assignment.latest_submission_status,
        latest_submission_version=assignment.latest_submission_version,
        latest_review_comment=assignment.latest_review_comment,
    )


def get_assignment_read(db: Session, assignment_id: str) -> AssignmentRead:
    return _assignment_read_from_row(db, _assignment_base_row(db, assignment_id))


def _active_assignment_for_paper(db: Session, paper_uuid: str):
    statement = text(
        """
        SELECT aa.id
        FROM annotation_assignments aa
        WHERE aa.paper_id = :paper_uuid AND aa.status IN :statuses
        ORDER BY aa.assigned_at DESC, aa.id DESC
        LIMIT 1
        """
    ).bindparams(bindparam("statuses", expanding=True))
    row = _execute(db, statement, {"paper_uuid": paper_uuid, "statuses": ASSIGNMENT_ACTIVE_STATUSES}).mappings().first()
    return row


def _ensure_assignment_owner(assignment: AssignmentRead, current_user: UserProfile) -> None:
    if current_user.role == UserRole.admin:
        return
    if current_user.role == UserRole.reviewer and assignment.reviewer_id == current_user.id:
        return
    if current_user.role == UserRole.annotator and assignment.annotator_id == current_user.id:
        return
    raise _forbidden("This assignment is not available to the current user")


def _ensure_reviewer_owner(assignment: AssignmentRead, current_user: UserProfile) -> None:
    if current_user.role == UserRole.admin:
        return
    if current_user.role == UserRole.reviewer and assignment.reviewer_id == current_user.id:
        return
    raise _forbidden("Reviewer access is required for this assignment")


def list_assignments(db: Session, current_user: UserProfile) -> list[AssignmentRead]:
    if current_user.role == UserRole.admin:
        where_sql = "1 = 1"
        params: dict[str, object] = {}
    elif current_user.role == UserRole.reviewer:
        where_sql = "aa.reviewer_id = :user_id"
        params = {"user_id": current_user.id}
    else:
        where_sql = "aa.annotator_id = :user_id"
        params = {"user_id": current_user.id}

    rows = _execute(db, text(f"""
        SELECT aa.id, aa.paper_id AS paper_uuid, aa.annotator_id, aa.reviewer_id, aa.status,
               aa.assigned_at, aa.started_at, aa.submitted_at, aa.completed_at, aa.due_at,
               p.paper_id, p.title AS paper_title, p.doi,
               annotator.full_name AS annotator_name, annotator.email AS annotator_email,
               reviewer.full_name AS reviewer_name, reviewer.email AS reviewer_email
        FROM annotation_assignments aa
        JOIN papers p ON p.id = aa.paper_id
        LEFT JOIN user_profiles annotator ON annotator.id = aa.annotator_id
        LEFT JOIN user_profiles reviewer ON reviewer.id = aa.reviewer_id
        WHERE {where_sql}
        ORDER BY aa.assigned_at DESC, aa.id DESC
    """), params).mappings().all()
    return [_assignment_read_from_row(db, row) for row in rows]


def assignment_options(db: Session, current_user: UserProfile) -> AssignmentOptionsResponse:
    if current_user.role not in {UserRole.reviewer, UserRole.admin}:
        raise _forbidden("Reviewer or admin privileges are required")

    paper_rows = _execute(db, text(
        """
        SELECT id, paper_id, title, doi
        FROM papers
        WHERE paper_id IS NOT NULL
        ORDER BY paper_id
        """
    )).mappings().all()
    papers: list[PaperSummary] = []
    for row in paper_rows:
        active = _active_assignment_for_paper(db, _row_value(row["id"]))
        assignment = get_assignment_read(db, _row_value(active["id"])) if active else None
        papers.append(PaperSummary(
            paper_id=_row_value(row["paper_id"]),
            title=_row_value(row["title"]),
            doi=_row_value(row["doi"]),
            has_edited_version=bool(assignment and assignment.latest_submission_status in {"draft", "review_draft"}),
            assignment=assignment_state_from_read(assignment),
        ))

    annotators = list(db.query(UserProfile).filter(
        UserProfile.role == UserRole.annotator,
        UserProfile.status == UserStatus.approved,
        UserProfile.is_active.is_(True),
        UserProfile.email_verified.is_(True),
    ).order_by(UserProfile.full_name.asc(), UserProfile.email.asc()).all())
    return AssignmentOptionsResponse(papers=papers, annotators=[UserRead.model_validate(item) for item in annotators])


def paper_assignment_history(db: Session, paper_id: str, current_user: UserProfile) -> PaperAssignmentHistoryResponse:
    if current_user.role not in {UserRole.reviewer, UserRole.admin}:
        raise _forbidden("Reviewer or admin privileges are required")

    paper = _paper_row_by_external_id(db, paper_id)
    paper_uuid = _row_value(paper["id"])
    active = _active_assignment_for_paper(db, paper_uuid)
    active_assignment = get_assignment_read(db, _row_value(active["id"])) if active else None

    rows = _execute(db, text(
        """
        SELECT aa.id, aa.paper_id AS paper_uuid, aa.annotator_id, aa.reviewer_id, aa.status,
               aa.assigned_at, aa.started_at, aa.submitted_at, aa.completed_at, aa.due_at,
               p.paper_id, p.title AS paper_title, p.doi,
               annotator.full_name AS annotator_name, annotator.email AS annotator_email,
               reviewer.full_name AS reviewer_name, reviewer.email AS reviewer_email
        FROM annotation_assignments aa
        JOIN papers p ON p.id = aa.paper_id
        LEFT JOIN user_profiles annotator ON annotator.id = aa.annotator_id
        LEFT JOIN user_profiles reviewer ON reviewer.id = aa.reviewer_id
        WHERE aa.paper_id = :paper_uuid
        ORDER BY aa.assigned_at DESC NULLS LAST, aa.id DESC
        """
    ), {"paper_uuid": paper_uuid}).mappings().all()
    assignments = [_assignment_read_from_row(db, row) for row in rows]
    for assignment in assignments:
        assignment.latest_review_comment = None

    return PaperAssignmentHistoryResponse(
        paper=PaperSummary(
            paper_id=_row_value(paper["paper_id"]),
            title=_row_value(paper["title"]),
            doi=_row_value(paper["doi"]),
            has_edited_version=bool(active_assignment and active_assignment.latest_submission_status in {"draft", "review_draft"}),
            assignment=assignment_state_from_read(active_assignment),
        ),
        assignments=assignments,
    )


def create_assignment(db: Session, payload: AssignmentCreateRequest, current_user: UserProfile) -> AssignmentRead:
    if current_user.role not in {UserRole.reviewer, UserRole.admin}:
        raise _forbidden("Reviewer or admin privileges are required")
    now = utc_now()
    if payload.due_at is not None and payload.due_at < now.date():
        raise _bad_request("Assignment due date cannot be earlier than today")
    annotator = db.get(UserProfile, payload.annotator_id)
    if annotator is None:
        raise _not_found("Annotator not found")
    if annotator.role != UserRole.annotator or annotator.status != UserStatus.approved or not annotator.is_active or not annotator.email_verified:
        raise _bad_request("Only approved, active, verified annotators can be assigned")

    paper = _paper_row_by_external_id(db, payload.paper_id)
    if _active_assignment_for_paper(db, _row_value(paper["id"])) is not None:
        raise _bad_request("This paper already has an active assignment")

    assignment_id = str(uuid4())
    try:
        _execute(db, text(
            """
            INSERT INTO annotation_assignments (id, paper_id, annotator_id, reviewer_id, status, assigned_at, started_at, submitted_at, completed_at, due_at)
            VALUES (:id, :paper_uuid, :annotator_id, :reviewer_id, 'assigned', :now, NULL, NULL, NULL, :due_at)
            """
        ), {
            "id": assignment_id,
            "paper_uuid": _row_value(paper["id"]),
            "annotator_id": annotator.id,
            "reviewer_id": current_user.id,
            "now": now,
            "due_at": payload.due_at,
        })
        _audit_event(db, current_user, "assignment.created", "annotation_assignments", assignment_id, {"paper_id": payload.paper_id, "annotator_id": annotator.id})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Assignment could not be created") from exc
    return get_assignment_read(db, assignment_id)


def cancel_assignment(db: Session, assignment_id: str, current_user: UserProfile) -> AssignmentRead:
    assignment = get_assignment_read(db, assignment_id)
    _ensure_reviewer_owner(assignment, current_user)
    if assignment.status == "approved":
        raise _bad_request("Approved assignments cannot be cancelled")
    if assignment.status == "cancelled":
        return assignment
    try:
        _execute(db, text("UPDATE annotation_assignments SET status = 'cancelled', completed_at = :now WHERE id = :assignment_id"), {"assignment_id": assignment_id, "now": utc_now()})
        _audit_event(db, current_user, "assignment.cancelled", "annotation_assignments", assignment_id, {})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Assignment could not be cancelled") from exc
    return get_assignment_read(db, assignment_id)


def assignment_for_paper_and_user(db: Session, paper_uuid: str, current_user: UserProfile) -> AssignmentRead | None:
    if current_user.role == UserRole.admin:
        statement = text(
            """
            SELECT id FROM annotation_assignments
            WHERE paper_id = :paper_uuid AND status IN :statuses
            ORDER BY assigned_at DESC, id DESC
            LIMIT 1
            """
        ).bindparams(bindparam("statuses", expanding=True))
        row = _execute(db, statement, {"paper_uuid": paper_uuid, "statuses": ASSIGNMENT_VISIBLE_STATUSES}).mappings().first()
        return get_assignment_read(db, _row_value(row["id"])) if row else None

    if current_user.role == UserRole.reviewer:
        statement = text(
            """
            SELECT id FROM annotation_assignments
            WHERE paper_id = :paper_uuid AND reviewer_id = :user_id AND status IN :statuses
            ORDER BY assigned_at DESC, id DESC
            LIMIT 1
            """
        ).bindparams(bindparam("statuses", expanding=True))
    else:
        statement = text(
            """
            SELECT id FROM annotation_assignments
            WHERE paper_id = :paper_uuid AND annotator_id = :user_id AND status IN :statuses
            ORDER BY assigned_at DESC, id DESC
            LIMIT 1
            """
        ).bindparams(bindparam("statuses", expanding=True))
    row = _execute(db, statement, {"paper_uuid": paper_uuid, "user_id": current_user.id, "statuses": ASSIGNMENT_VISIBLE_STATUSES}).mappings().first()
    return get_assignment_read(db, _row_value(row["id"])) if row else None


def visible_paper_uuids(db: Session, current_user: UserProfile) -> set[str] | None:
    if current_user.role in {UserRole.reviewer, UserRole.admin}:
        return None
    statement = text("""
        SELECT DISTINCT paper_id
        FROM annotation_assignments
        WHERE annotator_id = :user_id AND status <> 'cancelled'
    """)
    rows = _execute(db, statement, {"user_id": current_user.id}).all()
    return {_row_value(row[0]) for row in rows}


def ensure_paper_visible(db: Session, paper_uuid: str, current_user: UserProfile) -> AssignmentRead | None:
    if current_user.role in {UserRole.reviewer, UserRole.admin}:
        return assignment_for_paper_and_user(db, paper_uuid, current_user)
    assignment = assignment_for_paper_and_user(db, paper_uuid, current_user)
    if assignment is None:
        raise _forbidden("This paper is not assigned to the current user")
    return assignment


def ensure_editable_assignment_for_paper(db: Session, paper_uuid: str, current_user: UserProfile) -> AssignmentRead:
    assignment = assignment_for_paper_and_user(db, paper_uuid, current_user)
    if assignment is None:
        raise _forbidden("Create or open an active assignment before saving annotations")
    _ensure_assignment_owner(assignment, current_user)
    if current_user.role == UserRole.annotator:
        if assignment.status not in ASSIGNMENT_EDITABLE_STATUSES:
            raise _bad_request(f"This assignment is {assignment.status} and cannot be edited by the annotator")
    elif current_user.role in {UserRole.reviewer, UserRole.admin}:
        if assignment.status not in ASSIGNMENT_REVIEW_EDITABLE_STATUSES:
            raise _bad_request(f"This assignment is {assignment.status} and cannot be edited by the reviewer")
    else:
        raise _forbidden("This account cannot edit annotation submissions")
    return assignment


def mark_assignment_draft_saved(db: Session, assignment_id: str, editor_role: str) -> None:
    next_status = "review_in_progress" if editor_role == "reviewer" else "in_progress"
    _execute(db, text(
        """
        UPDATE annotation_assignments
        SET status = :next_status,
            started_at = COALESCE(started_at, :now)
        WHERE id = :assignment_id
        """
    ), {"assignment_id": assignment_id, "next_status": next_status, "now": utc_now()})


def submit_assignment(db: Session, assignment_id: str, current_user: UserProfile) -> SubmitResponse:
    assignment = get_assignment_read(db, assignment_id)
    if assignment.annotator_id != current_user.id:
        raise _forbidden("Only the assigned annotator can submit this assignment")
    if assignment.status not in ASSIGNMENT_EDITABLE_STATUSES:
        raise _bad_request(f"This assignment is {assignment.status} and cannot be submitted")
    draft = _latest_submission(db, assignment_id, ("draft",))
    if draft is None:
        raise _bad_request("Save a draft before submitting.")

    submission_id = _row_value(draft["id"])
    now = utc_now()
    try:
        _execute(db, text(
            """
            UPDATE annotation_submissions
            SET status = 'superseded'
            WHERE assignment_id = :assignment_id AND id <> :submission_id AND status = 'draft'
            """
        ), {"assignment_id": assignment_id, "submission_id": submission_id})
        _execute(db, text("UPDATE annotation_submissions SET status = 'submitted', submitted_at = :now WHERE id = :submission_id"), {"submission_id": submission_id, "now": now})
        _execute(db, text("UPDATE annotation_assignments SET status = 'submitted', submitted_at = :now WHERE id = :assignment_id"), {"assignment_id": assignment_id, "now": now})
        _audit_event(db, current_user, "assignment.submitted", "annotation_submissions", submission_id, {"assignment_id": assignment_id})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Assignment could not be submitted") from exc
    return SubmitResponse(assignment=get_assignment_read(db, assignment_id), submission_id=submission_id)


def _submission_summary_from_row(db: Session, row) -> ReviewSubmissionSummary:
    assignment = get_assignment_read(db, _row_value(row["assignment_id"]))
    return ReviewSubmissionSummary(
        submission_id=_row_value(row["id"]),
        assignment=assignment,
        version=int(row["version"] or 0),
        status=_row_value(row["status"]),
        created_at=row["created_at"],
        submitted_at=row["submitted_at"],
    )


def list_review_submissions(db: Session, current_user: UserProfile, status_filter: str = "submitted") -> list[ReviewSubmissionSummary]:
    if current_user.role not in {UserRole.reviewer, UserRole.admin}:
        raise _forbidden("Reviewer or admin privileges are required")
    if status_filter not in SUBMISSION_REVIEW_STATUSES:
        raise _bad_request("Unsupported review status")
    where_owner = "" if current_user.role == UserRole.admin else "AND aa.reviewer_id = :reviewer_id"
    status_clause = "sub.status IN ('submitted', 'review_draft')" if status_filter == "submitted" else "sub.status = :status"
    latest_clause = """
        AND NOT EXISTS (
            SELECT 1 FROM annotation_submissions newer
            WHERE newer.assignment_id = sub.assignment_id
              AND (newer.version > sub.version OR (newer.version = sub.version AND newer.created_at > sub.created_at))
        )
    """ if status_filter == "submitted" else ""
    rows = _execute(db, text(f"""
        SELECT sub.id, sub.assignment_id, sub.version, sub.status, sub.created_at, sub.submitted_at
        FROM annotation_submissions sub
        JOIN annotation_assignments aa ON aa.id = sub.assignment_id
        WHERE {status_clause} {latest_clause} {where_owner}
        ORDER BY sub.submitted_at DESC NULLS LAST, sub.created_at DESC, sub.version DESC
    """), {"status": status_filter, "reviewer_id": current_user.id}).mappings().all()
    return [_submission_summary_from_row(db, row) for row in rows]


def _submission_row(db: Session, submission_id: str):
    row = _execute(db, text(
        """
        SELECT id, assignment_id, version, status, parent_submission_id, created_by_id, editor_role, created_at, submitted_at
        FROM annotation_submissions
        WHERE id = :submission_id
        """
    ), {"submission_id": submission_id}).mappings().first()
    if row is None:
        raise _not_found("Submission not found")
    return row


def review_submission_detail(db: Session, submission_id: str, current_user: UserProfile) -> ReviewSubmissionDetail:
    row = _submission_row(db, submission_id)
    summary = _submission_summary_from_row(db, row)
    _ensure_reviewer_owner(summary.assignment, current_user)
    paper = db_editor_service.paper_detail_for_submission(db, submission_id, assignment_state_from_read(summary.assignment))
    decisions = _execute(db, text(
        """
        SELECT decision, comment, created_at
        FROM review_decisions
        WHERE submission_id = :submission_id
        ORDER BY created_at DESC, id DESC
        """
    ), {"submission_id": submission_id}).mappings().all()
    return ReviewSubmissionDetail(
        submission=summary,
        paper=paper,
        decisions=[{"decision": _row_value(item["decision"]), "comment": _row_value(item["comment"]), "created_at": _row_value(item["created_at"])} for item in decisions],
    )


def return_submission(db: Session, submission_id: str, payload: ReviewDecisionRequest, current_user: UserProfile) -> ReviewSubmissionSummary:
    row = _submission_row(db, submission_id)
    summary = _submission_summary_from_row(db, row)
    _ensure_reviewer_owner(summary.assignment, current_user)
    if summary.status not in {"submitted", "review_draft"}:
        raise _bad_request("Only submitted work or the current reviewer draft can be returned")
    latest = _latest_submission(db, summary.assignment.id)
    if latest is None or _row_value(latest["id"]) != submission_id:
        raise _bad_request("A newer revision exists. Refresh the editor before returning this work.")
    now = utc_now()
    try:
        _execute(db, text(
            """
            INSERT INTO review_decisions (id, submission_id, reviewer_id, decision, comment, created_at)
            VALUES (:id, :submission_id, :reviewer_id, 'returned', :comment, :now)
            """
        ), {"id": str(uuid4()), "submission_id": submission_id, "reviewer_id": current_user.id, "comment": payload.comment, "now": now})
        _execute(db, text("UPDATE annotation_submissions SET status = 'returned' WHERE id = :submission_id"), {"submission_id": submission_id})
        _execute(db, text("UPDATE annotation_assignments SET status = 'returned' WHERE id = :assignment_id"), {"assignment_id": summary.assignment.id})
        _audit_event(db, current_user, "submission.returned", "annotation_submissions", submission_id, {"assignment_id": summary.assignment.id})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Submission could not be returned") from exc
    return _submission_summary_from_row(db, _submission_row(db, submission_id))


def approve_submission(db: Session, submission_id: str, payload: ReviewDecisionRequest, current_user: UserProfile) -> ReviewSubmissionSummary:
    row = _submission_row(db, submission_id)
    summary = _submission_summary_from_row(db, row)
    _ensure_reviewer_owner(summary.assignment, current_user)
    if summary.status not in {"submitted", "review_draft"}:
        raise _bad_request("Only submitted work or the current reviewer draft can be approved")
    latest = _latest_submission(db, summary.assignment.id)
    if latest is None or _row_value(latest["id"]) != submission_id:
        raise _bad_request("A newer revision exists. Refresh the editor before approving this work.")
    now = utc_now()
    try:
        _copy_submission_to_final_annotations(db, submission_id, current_user.id, now)
        _execute(db, text(
            """
            INSERT INTO review_decisions (id, submission_id, reviewer_id, decision, comment, created_at)
            VALUES (:id, :submission_id, :reviewer_id, 'approved', :comment, :now)
            """
        ), {"id": str(uuid4()), "submission_id": submission_id, "reviewer_id": current_user.id, "comment": payload.comment, "now": now})
        _execute(db, text("UPDATE annotation_submissions SET status = 'approved' WHERE id = :submission_id"), {"submission_id": submission_id})
        _execute(db, text("UPDATE annotation_assignments SET status = 'approved', completed_at = :now WHERE id = :assignment_id"), {"assignment_id": summary.assignment.id, "now": now})
        _audit_event(db, current_user, "submission.approved", "annotation_submissions", submission_id, {"assignment_id": summary.assignment.id})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Submission could not be approved") from exc
    return _submission_summary_from_row(db, _submission_row(db, submission_id))


def _copy_submission_to_final_annotations(db: Session, submission_id: str, approved_by_id: str, approved_at: datetime) -> None:
    assignment_row = _execute(db, text(
        """
        SELECT aa.paper_id
        FROM annotation_submissions sub
        JOIN annotation_assignments aa ON aa.id = sub.assignment_id
        WHERE sub.id = :submission_id
        """
    ), {"submission_id": submission_id}).mappings().first()
    if assignment_row is None:
        raise _not_found("Submission not found")
    paper_uuid = _row_value(assignment_row["paper_id"])

    existing_final_ids = [_row_value(row[0]) for row in _execute(db, text("SELECT id FROM final_annotations WHERE paper_id = :paper_uuid"), {"paper_uuid": paper_uuid}).all()]
    if existing_final_ids:
        delete_support = text("DELETE FROM final_annotation_support_sentences WHERE final_annotation_id IN :ids").bindparams(bindparam("ids", expanding=True))
        _execute(db, delete_support, {"ids": existing_final_ids})
    _execute(db, text("DELETE FROM final_annotations WHERE paper_id = :paper_uuid"), {"paper_uuid": paper_uuid})

    relation_rows = _execute(db, text(
        """
        SELECT id, sentence_id, support_paragraph_id, subject_text, subject_type, predicate, object_text, object_type,
               confidence, evidence_text, relation_origin
        FROM annotation_submission_relations
        WHERE submission_id = :submission_id
        ORDER BY id
        """
    ), {"submission_id": submission_id}).mappings().all()
    for relation in relation_rows:
        final_id = str(uuid4())
        _execute(db, text(
            """
            INSERT INTO final_annotations (
                id, paper_id, approved_submission_id, source_submission_relation_id, approved_by_id,
                sentence_id, support_paragraph_id, subject_text, subject_type, predicate, object_text,
                object_type, confidence, evidence_text, relation_origin, approved_at
            ) VALUES (
                :id, :paper_uuid, :submission_id, :source_relation_id, :approved_by_id,
                :sentence_id, :support_paragraph_id, :subject_text, :subject_type, :predicate,
                :object_text, :object_type, :confidence, :evidence_text, :relation_origin, :approved_at
            )
            """
        ), {
            "id": final_id,
            "paper_uuid": paper_uuid,
            "submission_id": submission_id,
            "source_relation_id": _row_value(relation["id"]),
            "approved_by_id": approved_by_id,
            "sentence_id": relation["sentence_id"],
            "support_paragraph_id": relation["support_paragraph_id"],
            "subject_text": relation["subject_text"],
            "subject_type": relation["subject_type"],
            "predicate": relation["predicate"],
            "object_text": relation["object_text"],
            "object_type": relation["object_type"],
            "confidence": relation["confidence"],
            "evidence_text": relation["evidence_text"],
            "relation_origin": relation["relation_origin"],
            "approved_at": approved_at,
        })
        supports = _execute(db, text("SELECT sentence_id FROM annotation_relation_support_sentences WHERE submission_relation_id = :relation_id"), {"relation_id": _row_value(relation["id"])}).all()
        for support in supports:
            _execute(db, text(
                """
                INSERT INTO final_annotation_support_sentences (final_annotation_id, sentence_id)
                VALUES (:final_id, :sentence_id)
                """
            ), {"final_id": final_id, "sentence_id": support[0]})


def _can_export_paper(db: Session, paper_uuid: str, current_user: UserProfile) -> bool:
    if current_user.role in {UserRole.reviewer, UserRole.admin}:
        return True
    row = _execute(db, text(
        """
        SELECT 1
        FROM annotation_assignments
        WHERE paper_id = :paper_uuid AND annotator_id = :user_id AND status = 'approved'
        LIMIT 1
        """
    ), {"paper_uuid": paper_uuid, "user_id": current_user.id}).first()
    return row is not None


def export_final_annotations(db: Session, paper_id: str, export_format: str, current_user: UserProfile) -> ExportResult:
    export_format = export_format.lower().strip()
    if export_format not in {"csv", "json"}:
        raise _bad_request("Export format must be csv or json")
    paper = _paper_row_by_external_id(db, paper_id)
    paper_uuid = _row_value(paper["id"])
    if not _can_export_paper(db, paper_uuid, current_user):
        raise _forbidden("This final annotation export is not available to the current user")

    rows = _execute(db, text(
        """
        WITH latest_approved_submission AS (
            SELECT sub.id
            FROM annotation_submissions sub
            JOIN annotation_assignments aa ON aa.id = sub.assignment_id
            JOIN final_annotations candidate ON candidate.approved_submission_id = sub.id
            LEFT JOIN review_decisions rd
              ON rd.submission_id = sub.id AND rd.decision = 'approved'
            WHERE aa.paper_id = :paper_uuid AND sub.status = 'approved'
            GROUP BY sub.id, sub.version, sub.created_at, sub.submitted_at
            ORDER BY MAX(COALESCE(rd.created_at, candidate.approved_at)) DESC,
                     sub.version DESC,
                     sub.created_at DESC
            LIMIT 1
        )
        SELECT fa.id, fa.subject_text, fa.subject_type, fa.predicate, fa.object_text, fa.object_type,
               fa.evidence_text, fa.relation_origin, fa.approved_at, pa.paragraph_key
        FROM final_annotations fa
        JOIN latest_approved_submission latest ON latest.id = fa.approved_submission_id
        LEFT JOIN paragraphs pa ON pa.id = fa.support_paragraph_id
        WHERE fa.paper_id = :paper_uuid
        ORDER BY fa.approved_at, fa.id
        """
    ), {"paper_uuid": paper_uuid}).mappings().all()
    if not rows:
        raise _not_found("No final annotations are available for this paper")

    support_map = _final_support_sentence_map(db, [_row_value(row["id"]) for row in rows])
    records = []
    for row in rows:
        records.append({
            "paper_id": _row_value(paper["paper_id"]),
            "title": _row_value(paper["title"]),
            "doi": _row_value(paper["doi"]),
            "support_paragraph_id": _row_value(row["paragraph_key"]),
            "support_sentence_ids": ";".join(support_map.get(_row_value(row["id"]), [])),
            "subject_text": _row_value(row["subject_text"]),
            "subject_type": _row_value(row["subject_type"]),
            "predicate": _row_value(row["predicate"]),
            "object_text": _row_value(row["object_text"]),
            "object_type": _row_value(row["object_type"]),
            "evidence_text": _row_value(row["evidence_text"]),
            "relation_origin": _row_value(row["relation_origin"]),
            "approved_at": _row_value(row["approved_at"]),
        })

    now = utc_now()
    try:
        _execute(db, text(
            """
            INSERT INTO export_jobs (id, requested_by_id, paper_id, format, status, file_path, created_at, completed_at)
            VALUES (:id, :requested_by_id, :paper_uuid, :format, 'completed', :file_path, :now, :now)
            """
        ), {"id": str(uuid4()), "requested_by_id": current_user.id, "paper_uuid": paper_uuid, "format": export_format, "file_path": f"direct://{paper_id}.{export_format}", "now": now})
        _audit_event(db, current_user, "final_annotations.exported", "papers", paper_uuid, {"paper_id": paper_id, "format": export_format})
        db.commit()
    except SQLAlchemyError:
        db.rollback()

    filename = f"{paper_id}_final_annotations.{export_format}"
    if export_format == "json":
        return ExportResult(json.dumps(records, indent=2), "application/json", filename)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(records[0].keys()))
    writer.writeheader()
    writer.writerows(records)
    return ExportResult(buffer.getvalue(), "text/csv", filename)


def _final_support_sentence_map(db: Session, final_ids: list[str]) -> dict[str, list[str]]:
    if not final_ids:
        return {}
    statement = text(
        """
        SELECT support.final_annotation_id, se.sentence_key
        FROM final_annotation_support_sentences support
        JOIN sentences se ON se.id = support.sentence_id
        WHERE support.final_annotation_id IN :ids
        ORDER BY se.sentence_index NULLS LAST
        """
    ).bindparams(bindparam("ids", expanding=True))
    rows = _execute(db, statement, {"ids": final_ids}).mappings().all()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(_row_value(row["final_annotation_id"]), []).append(_row_value(row["sentence_key"]))
    return grouped


def _audit_event(db: Session, current_user: UserProfile, action: str, entity_type: str, entity_id: str, metadata: dict[str, object]) -> None:
    try:
        _execute(db, text(f"""
            INSERT INTO audit_events (id, actor_id, action, entity_type, entity_id, metadata, created_at)
            VALUES (:id, :actor_id, :action, :entity_type, :entity_id, {_json_expr(db)}, :created_at)
        """), {
            "id": str(uuid4()),
            "actor_id": current_user.id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metadata": _json_param(db, metadata),
            "created_at": utc_now(),
        })
    except SQLAlchemyError:
        # Audit logging must never be the reason the primary workflow fails.
        pass
