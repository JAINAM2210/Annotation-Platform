from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    annotator = "annotator"
    reviewer = "reviewer"
    admin = "admin"


class UserStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_class]


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()), index=True)
    firebase_uid: Mapped[str | None] = mapped_column(Text, unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=enum_values, native_enum=False),
        nullable=False,
        default=UserRole.annotator,
    )
    designation: Mapped[str | None] = mapped_column(Text, nullable=True)
    institute: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, values_callable=enum_values, native_enum=False),
        nullable=False,
        default=UserStatus.pending,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    approved_by: Mapped["UserProfile | None"] = relationship(remote_side=[id])


class PaperModel(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class SentenceModel(Base):
    __tablename__ = "sentences"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    sentence_key: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    sentence_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParagraphModel(Base):
    __tablename__ = "paragraphs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    paragraph_key: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParagraphSentenceModel(Base):
    __tablename__ = "paragraph_sentences"

    paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id", ondelete="CASCADE"), primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EntityMentionModel(Base):
    __tablename__ = "entity_mentions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    mention_key: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    sentence_id: Mapped[str | None] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ner_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RelationPredicateModel(Base):
    __tablename__ = "relation_predicates"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    predicate: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class SuggestionSetModel(Base):
    __tablename__ = "suggestion_sets"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    source_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_latest: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class SuggestedRelationModel(Base):
    __tablename__ = "suggested_relations"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    suggestion_set_id: Mapped[str | None] = mapped_column(ForeignKey("suggestion_sets.id", ondelete="CASCADE"), nullable=True)
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id"), nullable=True)
    relation_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentence_id: Mapped[str | None] = mapped_column(ForeignKey("sentences.id"), nullable=True)
    support_paragraph_id: Mapped[str | None] = mapped_column(ForeignKey("paragraphs.id"), nullable=True)
    subject_mention_id: Mapped[str | None] = mapped_column(ForeignKey("entity_mentions.id"), nullable=True)
    object_mention_id: Mapped[str | None] = mapped_column(ForeignKey("entity_mentions.id"), nullable=True)
    subject_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicate: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    relation_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    inherited_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SuggestedRelationSupportSentenceModel(Base):
    __tablename__ = "suggested_relation_support_sentences"

    suggested_relation_id: Mapped[str] = mapped_column(ForeignKey("suggested_relations.id", ondelete="CASCADE"), primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True)


class AnnotationAssignmentModel(Base):
    __tablename__ = "annotation_assignments"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id"), nullable=True)
    annotator_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnnotationSubmissionModel(Base):
    __tablename__ = "annotation_submissions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_assignments.id", ondelete="CASCADE"), nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnnotationSubmissionRelationModel(Base):
    __tablename__ = "annotation_submission_relations"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_submissions.id", ondelete="CASCADE"), nullable=True)
    suggested_relation_id: Mapped[str | None] = mapped_column(ForeignKey("suggested_relations.id"), nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentence_id: Mapped[str | None] = mapped_column(ForeignKey("sentences.id"), nullable=True)
    support_paragraph_id: Mapped[str | None] = mapped_column(ForeignKey("paragraphs.id"), nullable=True)
    subject_mention_id: Mapped[str | None] = mapped_column(ForeignKey("entity_mentions.id"), nullable=True)
    object_mention_id: Mapped[str | None] = mapped_column(ForeignKey("entity_mentions.id"), nullable=True)
    subject_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicate: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    relation_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    inherited_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AnnotationRelationSupportSentenceModel(Base):
    __tablename__ = "annotation_relation_support_sentences"

    submission_relation_id: Mapped[str] = mapped_column(ForeignKey("annotation_submission_relations.id", ondelete="CASCADE"), primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True)


class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_submissions.id", ondelete="CASCADE"), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class FinalAnnotationModel(Base):
    __tablename__ = "final_annotations"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=True)
    approved_submission_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_submissions.id"), nullable=True)
    source_submission_relation_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_submission_relations.id"), nullable=True)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    sentence_id: Mapped[str | None] = mapped_column(ForeignKey("sentences.id"), nullable=True)
    support_paragraph_id: Mapped[str | None] = mapped_column(ForeignKey("paragraphs.id"), nullable=True)
    subject_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicate: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    relation_origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class FinalAnnotationSupportSentenceModel(Base):
    __tablename__ = "final_annotation_support_sentences"

    final_annotation_id: Mapped[str] = mapped_column(ForeignKey("final_annotations.id", ondelete="CASCADE"), primary_key=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"), primary_key=True)


class ExportJobModel(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    paper_id: Mapped[str | None] = mapped_column(ForeignKey("papers.id"), nullable=True)
    format: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("user_profiles.id"), nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)



DatasetName = Literal["raw"]
EditorMode = Literal["sentence", "paragraph"]


class DatasetInfo(BaseModel):
    key: DatasetName
    label: str
    path: str


class PaperAssignmentState(BaseModel):
    assignment_id: str
    status: str
    annotator_id: str | None = None
    reviewer_id: str | None = None
    latest_submission_id: str | None = None
    latest_submission_status: str | None = None
    latest_submission_version: int | None = None
    latest_review_comment: str | None = None


class PaperSummary(BaseModel):
    paper_id: str
    title: str
    doi: str = ""
    has_edited_version: bool = False
    assignment: PaperAssignmentState | None = None


class SentenceRecord(BaseModel):
    sentence_id: str
    paper_id: str
    sentence_index: int
    text: str


class ParagraphRecord(BaseModel):
    paragraph_id: str
    paper_id: str
    paragraph_index: int
    text: str
    sentence_ids: list[str]


class MentionRecord(BaseModel):
    mention_id: str
    sentence_id: str
    paper_id: str
    text: str
    schema_type: str = ""
    ner_label: str = ""
    token_start: int | None = None
    token_end: int | None = None


class RelationRecord(BaseModel):
    relation_id: str
    sentence_id: str = ""
    paper_id: str
    paper_title: str
    doi: str = ""
    subject_text: str
    subject_type: str
    predicate: str
    object_text: str
    object_type: str
    confidence: float = Field(default=1.0)
    accepted: bool = True
    evidence_text: str = ""
    relation_origin: str = ""
    inherited_from: str = ""
    support_sentence_ids: str = ""
    support_paragraph_id: str = ""


class PaperDetailResponse(BaseModel):
    paper: PaperSummary
    sentences: list[SentenceRecord]
    paragraphs: list[ParagraphRecord]
    mentions: list[MentionRecord]
    relations: list[RelationRecord]
    source: str
    warnings: list[str] = Field(default_factory=list)
    assignment: PaperAssignmentState | None = None


class AssignmentCreateRequest(BaseModel):
    paper_id: str = Field(min_length=1, max_length=255)
    annotator_id: str = Field(min_length=1)
    due_at: datetime | None = None

    @field_validator("paper_id", "annotator_id")
    @classmethod
    def validate_assignment_text(cls, value: str) -> str:
        return value.strip()


class AssignmentRead(BaseModel):
    id: str
    paper_id: str
    paper_title: str
    doi: str = ""
    annotator_id: str | None = None
    annotator_name: str = ""
    annotator_email: str = ""
    reviewer_id: str | None = None
    reviewer_name: str = ""
    reviewer_email: str = ""
    status: str
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    due_at: datetime | None = None
    latest_submission_id: str | None = None
    latest_submission_status: str | None = None
    latest_submission_version: int | None = None
    latest_review_comment: str | None = None


class SubmitResponse(BaseModel):
    assignment: AssignmentRead
    submission_id: str


class ReviewDecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReviewSubmissionSummary(BaseModel):
    submission_id: str
    assignment: AssignmentRead
    version: int
    status: str
    created_at: datetime | None = None
    submitted_at: datetime | None = None


class ReviewSubmissionDetail(BaseModel):
    submission: ReviewSubmissionSummary
    paper: PaperDetailResponse
    decisions: list[dict[str, str | None]] = Field(default_factory=list)


class PaperEditorPayload(BaseModel):
    dataset: DatasetName
    paper_id: str
    editor_mode: EditorMode = "paragraph"
    relations: list[RelationRecord]


class AddRelationPayload(BaseModel):
    dataset: DatasetName
    paper_id: str
    relation: RelationRecord


class CustomPredicatePayload(BaseModel):
    predicate: str


def normalize_email(value: str) -> str:
    return value.strip().lower()


def clean_text(value: str | None) -> str:
    return (value or "").strip()


class RegisterProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.annotator
    designation: str = Field(default="", max_length=255)
    institute: str = Field(default="", max_length=255)
    state: str = Field(default="", max_length=255)
    country: str = Field(default="", max_length=255)

    @field_validator("full_name", "designation", "institute", "state", "country")
    @classmethod
    def validate_text_field(cls, value: str) -> str:
        return value.strip()


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: UserRole
    designation: str = ""
    institute: str = ""
    state: str = ""
    country: str = ""
    status: UserStatus
    is_active: bool
    email_verified: bool
    approved_by_id: str | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    email_verified_at: datetime | None

    @field_validator("designation", "institute", "state", "country", mode="before")
    @classmethod
    def default_empty_text(cls, value: str | None) -> str:
        return clean_text(value)


class AssignmentOptionsResponse(BaseModel):
    papers: list[PaperSummary]
    annotators: list[UserRead]


class PaperAssignmentHistoryResponse(BaseModel):
    paper: PaperSummary
    assignments: list[AssignmentRead]
