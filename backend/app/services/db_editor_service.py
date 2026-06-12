from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.data_errors import DataServiceError
from app.models import (
    DatasetInfo,
    MentionRecord,
    ParagraphRecord,
    PaperAssignmentState,
    PaperDetailResponse,
    PaperSummary,
    RelationRecord,
    SentenceRecord,
    UserProfile,
)


DATASET_INFO = DatasetInfo(key="raw", label="Aiven PostgreSQL", path="postgresql")


@dataclass(frozen=True)
class PaperDbIdentity:
    uuid: str
    paper_id: str
    title: str
    doi: str


@dataclass(frozen=True)
class ParagraphInferenceDiagnostics:
    total_paragraphs: int
    zero_paragraph_indexes: list[int]
    skipped_sentence_indexes: list[int]


@dataclass(frozen=True)
class ParagraphInferenceResult:
    sentence_ids_by_paragraph: dict[str, list[str]]
    diagnostics: ParagraphInferenceDiagnostics


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


def _bool_value(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    return bool(value)


def _json_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


_DASH_TRANSLATION = str.maketrans({
    "\u00ad": "",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
})
_MIN_SENTENCE_COMPACT_CHARS = 12
_MAX_POST_MATCH_MISSES = 20


def _normalize_editor_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").translate(_DASH_TRANSLATION)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _compact_editor_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_editor_text(value))


def _sentence_match_position(
    paragraph_norm: str,
    paragraph_compact: str,
    sentence_norm: str,
    sentence_compact: str,
) -> int:
    if not sentence_norm or len(sentence_compact) < _MIN_SENTENCE_COMPACT_CHARS:
        return -1

    position = paragraph_norm.find(sentence_norm)
    if position >= 0:
        return position

    if len(sentence_compact) >= 24:
        compact_position = paragraph_compact.find(sentence_compact)
        if compact_position >= 0:
            return compact_position

    return -1


def _infer_sentence_ids_for_paragraphs(paragraphs: list[ParagraphRecord], sentences: list[SentenceRecord]) -> ParagraphInferenceResult:
    inferred: dict[str, list[str]] = {paragraph.paragraph_id: [] for paragraph in paragraphs}
    zero_indexes: list[int] = []
    skipped_indexes: list[int] = []
    if not paragraphs or not sentences:
        return ParagraphInferenceResult(
            sentence_ids_by_paragraph=inferred,
            diagnostics=ParagraphInferenceDiagnostics(
                total_paragraphs=len(paragraphs),
                zero_paragraph_indexes=[paragraph.paragraph_index for paragraph in paragraphs],
                skipped_sentence_indexes=[],
            ),
        )

    sentence_cursor = 0
    sentence_norms = [_normalize_editor_text(sentence.text) for sentence in sentences]
    sentence_compacts = [_compact_editor_text(sentence.text) for sentence in sentences]

    for paragraph in paragraphs:
        paragraph_norm = _normalize_editor_text(paragraph.text)
        paragraph_compact = _compact_editor_text(paragraph.text)
        if not paragraph_norm:
            zero_indexes.append(paragraph.paragraph_index)
            continue

        matches: list[int] = []
        post_match_misses = 0
        for sentence_index in range(sentence_cursor, len(sentences)):
            position = _sentence_match_position(
                paragraph_norm,
                paragraph_compact,
                sentence_norms[sentence_index],
                sentence_compacts[sentence_index],
            )
            if position >= 0:
                matches.append(sentence_index)
                post_match_misses = 0
                continue

            if matches:
                post_match_misses += 1
                if post_match_misses >= _MAX_POST_MATCH_MISSES:
                    break

        if matches:
            inferred[paragraph.paragraph_id] = [sentences[sentence_index].sentence_id for sentence_index in matches]

            last_seen = sentence_cursor - 1
            for matched_index in matches:
                if matched_index > last_seen + 1:
                    skipped_indexes.extend(sentences[index].sentence_index for index in range(last_seen + 1, matched_index))
                last_seen = matched_index
            sentence_cursor = matches[-1] + 1
        else:
            zero_indexes.append(paragraph.paragraph_index)

    return ParagraphInferenceResult(
        sentence_ids_by_paragraph=inferred,
        diagnostics=ParagraphInferenceDiagnostics(
            total_paragraphs=len(paragraphs),
            zero_paragraph_indexes=zero_indexes,
            skipped_sentence_indexes=sorted(set(skipped_indexes)),
        ),
    )


def _db_error(message: str, *, code: str = "editor_database_error", hint: str = "Check that the Aiven editor tables are present and populated.", paper_id: str | None = None) -> DataServiceError:
    return DataServiceError(503, code, message, hint, paper_id)


def _execute(db: Session, statement, params: dict | None = None):
    return db.execute(statement, params or {})


def list_datasets() -> list[DatasetInfo]:
    return [DATASET_INFO]


def list_papers(db: Session, current_user: UserProfile | None = None) -> list[PaperSummary]:
    visible_uuids: set[str] | None = None
    if current_user is not None:
        from app.services import workflow_service

        visible_uuids = workflow_service.visible_paper_uuids(db, current_user)
        if visible_uuids == set():
            return []

    try:
        if visible_uuids is None:
            rows = _execute(db, text(
                """
                SELECT p.id, p.paper_id, p.title, p.doi,
                       EXISTS (
                         SELECT 1
                         FROM annotation_submissions sub
                         JOIN annotation_assignments aa ON aa.id = sub.assignment_id
                         WHERE aa.paper_id = p.id AND sub.status = 'draft'
                       ) AS has_edited_version
                FROM papers p
                WHERE p.paper_id IS NOT NULL
                ORDER BY p.paper_id
                """
            )).mappings().all()
        else:
            statement = text(
                """
                SELECT p.id, p.paper_id, p.title, p.doi,
                       EXISTS (
                         SELECT 1
                         FROM annotation_submissions sub
                         JOIN annotation_assignments aa ON aa.id = sub.assignment_id
                         WHERE aa.paper_id = p.id AND sub.status = 'draft'
                       ) AS has_edited_version
                FROM papers p
                WHERE p.id IN :paper_ids AND p.paper_id IS NOT NULL
                ORDER BY p.paper_id
                """
            ).bindparams(bindparam("paper_ids", expanding=True))
            rows = _execute(db, statement, {"paper_ids": list(visible_uuids)}).mappings().all()
    except SQLAlchemyError as exc:
        raise _db_error(
            "Paper list could not be loaded from the platform database.",
            code="paper_list_unavailable",
            hint="Check the papers and annotation_submissions tables in Aiven.",
        ) from exc

    summaries: list[PaperSummary] = []
    for row in rows:
        assignment_state: PaperAssignmentState | None = None
        if current_user is not None:
            from app.services import workflow_service

            assignment = workflow_service.assignment_for_paper_and_user(db, _row_value(row["id"]), current_user)
            assignment_state = workflow_service.assignment_state_from_read(assignment)
        summaries.append(PaperSummary(
            paper_id=_row_value(row["paper_id"]),
            title=_row_value(row["title"]),
            doi=_row_value(row["doi"]),
            has_edited_version=bool(row["has_edited_version"]),
            assignment=assignment_state,
        ))
    return summaries

def _paper_identity(db: Session, paper_id: str) -> PaperDbIdentity:
    try:
        row = _execute(db, text(
            """
            SELECT id, paper_id, title, doi
            FROM papers
            WHERE paper_id = :paper_id
            """
        ), {"paper_id": paper_id}).mappings().first()
    except SQLAlchemyError as exc:
        raise _db_error(
            "Paper metadata could not be loaded from the platform database.",
            code="paper_metadata_unavailable",
            hint="Check the papers table in Aiven.",
            paper_id=paper_id,
        ) from exc

    if row is None:
        raise DataServiceError(
            404,
            "paper_not_found",
            "Paper not found.",
            "Check that this paper_id exists in the papers table.",
            paper_id,
        )

    return PaperDbIdentity(
        uuid=_row_value(row["id"]),
        paper_id=_row_value(row["paper_id"]),
        title=_row_value(row["title"]),
        doi=_row_value(row["doi"]),
    )


def _safe_section(warnings: list[str], message: str, hint: str, action, fallback):
    try:
        return action()
    except SQLAlchemyError:
        warnings.append(f"{message} {hint}")
        return fallback


def _load_sentences(db: Session, paper: PaperDbIdentity, warnings: list[str]) -> tuple[list[SentenceRecord], dict[str, str], dict[str, str]]:
    def query():
        return _execute(db, text(
            """
            SELECT id, sentence_key, sentence_index, text
            FROM sentences
            WHERE paper_id = :paper_uuid
            ORDER BY sentence_index NULLS LAST, sentence_key, id
            """
        ), {"paper_uuid": paper.uuid}).mappings().all()

    rows = _safe_section(
        warnings,
        "Sentences could not be loaded for this paper.",
        "Ask the database loader to check the sentences table.",
        query,
        [],
    )

    records: list[SentenceRecord] = []
    uuid_to_key: dict[str, str] = {}
    key_to_uuid: dict[str, str] = {}
    for row in rows:
        db_id = _row_value(row["id"])
        external_id = _row_value(row["sentence_key"], db_id) or db_id
        uuid_to_key[db_id] = external_id
        key_to_uuid[external_id] = db_id
        records.append(SentenceRecord(
            sentence_id=external_id,
            paper_id=paper.paper_id,
            sentence_index=int(row["sentence_index"] or len(records) + 1),
            text=_row_value(row["text"]),
        ))

    if not records:
        warnings.append("No sentences are available for this paper yet. Ask the database loader to populate sentences before annotation.")

    return records, uuid_to_key, key_to_uuid


def _load_paragraphs(
    db: Session,
    paper: PaperDbIdentity,
    sentences: list[SentenceRecord],
    sentence_uuid_to_key: dict[str, str],
    warnings: list[str],
) -> tuple[list[ParagraphRecord], dict[str, str], dict[str, str], dict[str, str]]:
    def query():
        return _execute(db, text(
            """
            SELECT id AS paragraph_uuid,
                   paragraph_key,
                   paragraph_index,
                   text AS paragraph_text
            FROM paragraphs
            WHERE paper_id = :paper_uuid
            ORDER BY paragraph_index NULLS LAST, paragraph_key, id
            """
        ), {"paper_uuid": paper.uuid}).mappings().all()

    rows = _safe_section(
        warnings,
        "Paragraphs could not be loaded for this paper.",
        "Ask the database loader to check the paragraphs table.",
        query,
        [],
    )

    paragraphs: list[ParagraphRecord] = []
    paragraph_uuid_to_key: dict[str, str] = {}
    paragraph_key_to_uuid: dict[str, str] = {}
    sentence_uuid_to_paragraph_key: dict[str, str] = {}
    sentence_key_to_uuid = {sentence_key: sentence_uuid for sentence_uuid, sentence_key in sentence_uuid_to_key.items()}

    for row in rows:
        paragraph_uuid = _row_value(row["paragraph_uuid"])
        paragraph_key = _row_value(row["paragraph_key"], paragraph_uuid) or paragraph_uuid
        paragraph_uuid_to_key[paragraph_uuid] = paragraph_key
        paragraph_key_to_uuid[paragraph_key] = paragraph_uuid
        paragraphs.append(ParagraphRecord(
            paragraph_id=paragraph_key,
            paper_id=paper.paper_id,
            paragraph_index=int(row["paragraph_index"] or len(paragraphs) + 1),
            text=_row_value(row["paragraph_text"]),
            sentence_ids=[],
        ))

    inference = _infer_sentence_ids_for_paragraphs(paragraphs, sentences)
    inferred_count = 0
    for paragraph in paragraphs:
        paragraph.sentence_ids = inference.sentence_ids_by_paragraph.get(paragraph.paragraph_id, [])
        inferred_count += len(paragraph.sentence_ids)
        for sentence_key in paragraph.sentence_ids:
            sentence_uuid = sentence_key_to_uuid.get(sentence_key)
            if sentence_uuid:
                sentence_uuid_to_paragraph_key[sentence_uuid] = paragraph.paragraph_id

    if paragraphs and sentences and inference.diagnostics.zero_paragraph_indexes:
        preview = ", ".join(str(index) for index in inference.diagnostics.zero_paragraph_indexes[:8])
        suffix = "" if len(inference.diagnostics.zero_paragraph_indexes) <= 8 else ", ..."
        warnings.append(f"Entity highlights could not be inferred for paragraph(s): {preview}{suffix}. The paragraph text and relations are still available.")
    elif paragraphs and sentences and inferred_count == 0:
        warnings.append("Sentence membership could not be inferred for these paragraphs. The editor can show paragraph text, but entity highlights may be unavailable for this paper.")

    if not paragraphs and sentences:
        warnings.append("No paragraphs are available for this paper. The editor is temporarily showing one paragraph per sentence.")
        for sentence in sentences:
            synthetic_id = f"{paper.paper_id}:synthetic-p{sentence.sentence_index:04d}"
            paragraphs.append(ParagraphRecord(
                paragraph_id=synthetic_id,
                paper_id=paper.paper_id,
                paragraph_index=sentence.sentence_index,
                text=sentence.text,
                sentence_ids=[sentence.sentence_id],
            ))

    return paragraphs, paragraph_uuid_to_key, paragraph_key_to_uuid, sentence_uuid_to_paragraph_key

def _load_mentions(
    db: Session,
    paper: PaperDbIdentity,
    sentence_uuid_to_key: dict[str, str],
    warnings: list[str],
) -> tuple[list[MentionRecord], dict[str, str]]:
    def query():
        return _execute(db, text(
            """
            SELECT em.id AS mention_uuid,
                   em.mention_key,
                   em.text,
                   em.ner_label,
                   em.schema_type,
                   em.token_start,
                   em.token_end,
                   se.id AS sentence_uuid,
                   se.sentence_key
            FROM entity_mentions em
            JOIN sentences se ON se.id = em.sentence_id
            WHERE se.paper_id = :paper_uuid
            ORDER BY se.sentence_index NULLS LAST, em.token_start NULLS LAST, em.token_end NULLS LAST, em.mention_key
            """
        ), {"paper_uuid": paper.uuid}).mappings().all()

    rows = _safe_section(
        warnings,
        "Entity mentions could not be loaded for this paper.",
        "Ask the database loader to check entity_mentions sentence links.",
        query,
        [],
    )

    records: list[MentionRecord] = []
    key_to_uuid: dict[str, str] = {}
    for row in rows:
        mention_uuid = _row_value(row["mention_uuid"])
        mention_key = _row_value(row["mention_key"], mention_uuid) or mention_uuid
        sentence_uuid = _row_value(row["sentence_uuid"])
        sentence_key = _row_value(row["sentence_key"], sentence_uuid_to_key.get(sentence_uuid, sentence_uuid))
        key_to_uuid[mention_key] = mention_uuid
        records.append(MentionRecord(
            mention_id=mention_key,
            sentence_id=sentence_key,
            paper_id=paper.paper_id,
            text=_row_value(row["text"]),
            schema_type=_row_value(row["schema_type"]),
            ner_label=_row_value(row["ner_label"]),
            token_start=None if row["token_start"] is None else int(row["token_start"]),
            token_end=None if row["token_end"] is None else int(row["token_end"]),
        ))

    if not records:
        warnings.append("No entity mentions are available for this paper yet. You can still inspect text, but highlighted entity selection will be unavailable.")

    return records, key_to_uuid


def _support_sentence_ids(db: Session, table_name: str, relation_column: str, relation_ids: list[str], sentence_uuid_to_key: dict[str, str]) -> dict[str, list[str]]:
    if not relation_ids:
        return {}
    statement = text(
        f"""
        SELECT support.{relation_column} AS relation_id, se.id AS sentence_uuid, se.sentence_key
        FROM {table_name} support
        JOIN sentences se ON se.id = support.sentence_id
        WHERE support.{relation_column} IN :relation_ids
        ORDER BY se.sentence_index NULLS LAST
        """
    ).bindparams(bindparam("relation_ids", expanding=True))
    rows = _execute(db, statement, {"relation_ids": relation_ids}).mappings().all()
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        relation_id = _row_value(row["relation_id"])
        sentence_uuid = _row_value(row["sentence_uuid"])
        grouped[relation_id].append(_row_value(row["sentence_key"], sentence_uuid_to_key.get(sentence_uuid, sentence_uuid)))
    return grouped


def _relation_record_from_row(
    row,
    *,
    paper: PaperDbIdentity,
    sentence_uuid_to_key: dict[str, str],
    paragraph_uuid_to_key: dict[str, str],
    sentence_uuid_to_paragraph_key: dict[str, str],
    support_sentence_ids: list[str],
    source: str,
) -> RelationRecord:
    relation_uuid = _row_value(row["relation_uuid"])
    raw_payload = _json_payload(row.get("raw_payload"))
    relation_key = _row_value(raw_payload.get("relation_id")) or _row_value(row.get("relation_key")) or relation_uuid

    sentence_uuid = _row_value(row.get("sentence_uuid"))
    sentence_id = _row_value(row.get("sentence_key"), sentence_uuid_to_key.get(sentence_uuid, sentence_uuid))
    paragraph_uuid = _row_value(row.get("paragraph_uuid"))
    paragraph_id = _row_value(row.get("paragraph_key"), paragraph_uuid_to_key.get(paragraph_uuid, ""))
    if not paragraph_id and sentence_uuid:
        paragraph_id = sentence_uuid_to_paragraph_key.get(sentence_uuid, "")

    if not support_sentence_ids and sentence_id:
        support_sentence_ids = [sentence_id]

    return RelationRecord(
        relation_id=relation_key,
        sentence_id=sentence_id,
        paper_id=paper.paper_id,
        paper_title=paper.title,
        doi=paper.doi,
        subject_text=_row_value(row.get("subject_text")),
        subject_type=_row_value(row.get("subject_type")),
        predicate=_row_value(row.get("predicate")),
        object_text=_row_value(row.get("object_text")),
        object_type=_row_value(row.get("object_type")),
        confidence=_float_value(row.get("confidence")),
        accepted=_bool_value(row.get("accepted")),
        evidence_text=_row_value(row.get("evidence_text")),
        relation_origin=_row_value(row.get("relation_origin"), source),
        inherited_from=_row_value(row.get("inherited_from")),
        support_sentence_ids=";".join(support_sentence_ids),
        support_paragraph_id=paragraph_id,
    )


def _load_submission_relations(
    db: Session,
    submission_id: str,
    paper: PaperDbIdentity,
    sentence_uuid_to_key: dict[str, str],
    paragraph_uuid_to_key: dict[str, str],
    sentence_uuid_to_paragraph_key: dict[str, str],
) -> list[RelationRecord]:
    rows = _execute(db, text(
        """
        SELECT ar.id AS relation_uuid,
               sr.relation_key,
               ar.sentence_id AS sentence_uuid,
               se.sentence_key,
               ar.support_paragraph_id AS paragraph_uuid,
               pa.paragraph_key,
               ar.subject_text,
               ar.subject_type,
               ar.predicate,
               ar.object_text,
               ar.object_type,
               ar.confidence,
               ar.accepted,
               ar.evidence_text,
               ar.relation_origin,
               ar.inherited_from,
               ar.raw_payload
        FROM annotation_submission_relations ar
        LEFT JOIN suggested_relations sr ON sr.id = ar.suggested_relation_id
        LEFT JOIN sentences se ON se.id = ar.sentence_id
        LEFT JOIN paragraphs pa ON pa.id = ar.support_paragraph_id
        WHERE ar.submission_id = :submission_id
        ORDER BY ar.id
        """
    ), {"submission_id": submission_id}).mappings().all()

    support = _support_sentence_ids(db, "annotation_relation_support_sentences", "submission_relation_id", [_row_value(row["relation_uuid"]) for row in rows], sentence_uuid_to_key)
    return [
        _relation_record_from_row(
            row,
            paper=paper,
            sentence_uuid_to_key=sentence_uuid_to_key,
            paragraph_uuid_to_key=paragraph_uuid_to_key,
            sentence_uuid_to_paragraph_key=sentence_uuid_to_paragraph_key,
            support_sentence_ids=support.get(_row_value(row["relation_uuid"]), []),
            source="submission",
        )
        for row in rows
    ]


def _latest_assignment_submission(db: Session, assignment_id: str):
    return _execute(db, text(
        """
        SELECT id, status
        FROM annotation_submissions
        WHERE assignment_id = :assignment_id AND status IN ('draft', 'submitted', 'returned', 'approved')
        ORDER BY version DESC, created_at DESC, id DESC
        LIMIT 1
        """
    ), {"assignment_id": assignment_id}).mappings().first()


def _load_assignment_relations(
    db: Session,
    assignment: PaperAssignmentState | None,
    paper: PaperDbIdentity,
    sentence_uuid_to_key: dict[str, str],
    paragraph_uuid_to_key: dict[str, str],
    sentence_uuid_to_paragraph_key: dict[str, str],
) -> tuple[list[RelationRecord], str]:
    if assignment is None:
        return [], "none"
    latest = _latest_assignment_submission(db, assignment.assignment_id)
    if latest is None:
        return [], "none"
    relations = _load_submission_relations(db, _row_value(latest["id"]), paper, sentence_uuid_to_key, paragraph_uuid_to_key, sentence_uuid_to_paragraph_key)
    return relations, _row_value(latest["status"], "submission")

def _load_suggested_relations(
    db: Session,
    paper: PaperDbIdentity,
    sentence_uuid_to_key: dict[str, str],
    paragraph_uuid_to_key: dict[str, str],
    sentence_uuid_to_paragraph_key: dict[str, str],
) -> list[RelationRecord]:
    base_sql = """
        SELECT sr.id AS relation_uuid,
               sr.relation_key,
               sr.sentence_id AS sentence_uuid,
               se.sentence_key,
               sr.support_paragraph_id AS paragraph_uuid,
               pa.paragraph_key,
               sr.subject_text,
               sr.subject_type,
               sr.predicate,
               sr.object_text,
               sr.object_type,
               sr.confidence,
               sr.accepted,
               sr.evidence_text,
               sr.relation_origin,
               sr.inherited_from,
               NULL AS raw_payload
        FROM suggested_relations sr
        JOIN suggestion_sets ss ON ss.id = sr.suggestion_set_id
        LEFT JOIN sentences se ON se.id = sr.sentence_id
        LEFT JOIN paragraphs pa ON pa.id = sr.support_paragraph_id
    """
    rows = _execute(db, text(base_sql + """
        WHERE ss.paper_id = :paper_uuid AND COALESCE(ss.is_latest, TRUE) = TRUE
        ORDER BY pa.paragraph_index NULLS LAST, se.sentence_index NULLS LAST, sr.relation_key, sr.id
        """), {"paper_uuid": paper.uuid}).mappings().all()

    if not rows:
        rows = _execute(db, text(base_sql + """
            WHERE ss.paper_id = :paper_uuid
            ORDER BY pa.paragraph_index NULLS LAST, se.sentence_index NULLS LAST, sr.relation_key, sr.id
            """), {"paper_uuid": paper.uuid}).mappings().all()

    support = _support_sentence_ids(db, "suggested_relation_support_sentences", "suggested_relation_id", [_row_value(row["relation_uuid"]) for row in rows], sentence_uuid_to_key)
    return [
        _relation_record_from_row(
            row,
            paper=paper,
            sentence_uuid_to_key=sentence_uuid_to_key,
            paragraph_uuid_to_key=paragraph_uuid_to_key,
            sentence_uuid_to_paragraph_key=sentence_uuid_to_paragraph_key,
            support_sentence_ids=support.get(_row_value(row["relation_uuid"]), []),
            source="suggestion",
        )
        for row in rows
    ]

def _paper_detail_payload(
    db: Session,
    paper_id: str,
    *,
    current_user: UserProfile | None = None,
    assignment_state: PaperAssignmentState | None = None,
    submission_id: str | None = None,
) -> PaperDetailResponse:
    warnings: list[str] = []
    paper = _paper_identity(db, paper_id)
    if current_user is not None:
        from app.services import workflow_service

        assignment = workflow_service.ensure_paper_visible(db, paper.uuid, current_user)
        assignment_state = workflow_service.assignment_state_from_read(assignment)

    sentences, sentence_uuid_to_key, sentence_key_to_uuid = _load_sentences(db, paper, warnings)
    paragraphs, paragraph_uuid_to_key, paragraph_key_to_uuid, sentence_uuid_to_paragraph_key = _load_paragraphs(db, paper, sentences, sentence_uuid_to_key, warnings)
    mentions, mention_key_to_uuid = _load_mentions(db, paper, sentence_uuid_to_key, warnings)

    source = "source"
    relations: list[RelationRecord]
    try:
        if submission_id:
            relations = _load_submission_relations(db, submission_id, paper, sentence_uuid_to_key, paragraph_uuid_to_key, sentence_uuid_to_paragraph_key)
            source = "submission"
        else:
            relations, source = _load_assignment_relations(db, assignment_state, paper, sentence_uuid_to_key, paragraph_uuid_to_key, sentence_uuid_to_paragraph_key)
            if not relations:
                relations = _load_suggested_relations(db, paper, sentence_uuid_to_key, paragraph_uuid_to_key, sentence_uuid_to_paragraph_key)
                source = "source" if relations else "none"
    except SQLAlchemyError:
        warnings.append("Relations could not be loaded for this paper. You can still inspect the paper text.")
        relations = []
        source = "none"

    if not relations:
        warnings.append("No relation suggestions are available for this paper yet. You can still inspect the paper text.")

    del sentence_key_to_uuid, paragraph_key_to_uuid, mention_key_to_uuid
    summary = PaperSummary(paper_id=paper.paper_id, title=paper.title, doi=paper.doi, has_edited_version=source in {"draft", "submission"}, assignment=assignment_state)
    return PaperDetailResponse(
        paper=summary,
        sentences=sentences,
        paragraphs=paragraphs,
        mentions=mentions,
        relations=relations,
        source=source,
        warnings=warnings,
        assignment=assignment_state,
    )


def paper_detail(db: Session, paper_id: str, current_user: UserProfile | None = None) -> PaperDetailResponse:
    return _paper_detail_payload(db, paper_id, current_user=current_user)


def paper_detail_for_submission(db: Session, submission_id: str, assignment_state: PaperAssignmentState | None = None) -> PaperDetailResponse:
    row = _execute(db, text(
        """
        SELECT p.paper_id
        FROM annotation_submissions sub
        JOIN annotation_assignments aa ON aa.id = sub.assignment_id
        JOIN papers p ON p.id = aa.paper_id
        WHERE sub.id = :submission_id
        """
    ), {"submission_id": submission_id}).mappings().first()
    if row is None:
        raise DataServiceError(404, "submission_not_found", "Submission not found.", "Check annotation_submissions in Aiven.")
    return _paper_detail_payload(db, _row_value(row["paper_id"]), assignment_state=assignment_state, submission_id=submission_id)

def list_schema_predicates(db: Session, *, direct_only: bool = False) -> list[str]:
    try:
        predicate_values: set[str] = set()
        relation_rows = _execute(db, text(
            """
            SELECT predicate
            FROM relation_predicates
            WHERE predicate IS NOT NULL AND trim(predicate) <> ''
            ORDER BY lower(predicate)
            """
        )).all()
        predicate_values.update(_row_value(row[0]).strip() for row in relation_rows if _row_value(row[0]).strip())

        if not direct_only:
            suggestion_rows = _execute(db, text(
                """
                SELECT DISTINCT predicate
                FROM suggested_relations
                WHERE predicate IS NOT NULL AND trim(predicate) <> ''
                ORDER BY lower(predicate)
                """
            )).all()
            predicate_values.update(_row_value(row[0]).strip() for row in suggestion_rows if _row_value(row[0]).strip())
    except SQLAlchemyError as exc:
        raise _db_error(
            "Relation predicates could not be loaded from the platform database.",
            code="relation_predicates_unavailable",
            hint="Check relation_predicates and suggested_relations in Aiven.",
        ) from exc
    return sorted(predicate_values, key=str.lower)

def save_custom_schema_predicate(db: Session, predicate: str, current_user: UserProfile) -> list[str]:
    cleaned = predicate.strip()
    if not cleaned:
        return list_schema_predicates(db, direct_only=True)
    try:
        existing = _execute(db, text("SELECT id FROM relation_predicates WHERE lower(predicate) = lower(:predicate) LIMIT 1"), {"predicate": cleaned}).first()
        if existing is None:
            _execute(db, text(
                """
                INSERT INTO relation_predicates (id, predicate, subject_type, object_type, is_custom, created_by_id, created_at)
                VALUES (:id, :predicate, 'custom', 'custom', :is_custom, :created_by_id, :created_at)
                """
            ), {
                "id": str(uuid4()),
                "predicate": cleaned,
                "is_custom": True,
                "created_by_id": current_user.id,
                "created_at": datetime.now(timezone.utc),
            })
            db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _db_error(
            "Custom relation predicate could not be saved.",
            code="relation_predicate_save_failed",
            hint="Check write access and the relation_predicates table in Aiven.",
        ) from exc
    return list_schema_predicates(db, direct_only=True)


def _identity_maps_for_paper(db: Session, paper_uuid: str) -> dict[str, dict[str, str]]:
    sentences = _execute(db, text("SELECT id, sentence_key FROM sentences WHERE paper_id = :paper_uuid"), {"paper_uuid": paper_uuid}).mappings().all()
    paragraphs = _execute(db, text("SELECT id, paragraph_key FROM paragraphs WHERE paper_id = :paper_uuid"), {"paper_uuid": paper_uuid}).mappings().all()
    mentions = _execute(db, text(
        """
        SELECT em.id, em.mention_key
        FROM entity_mentions em
        JOIN sentences se ON se.id = em.sentence_id
        WHERE se.paper_id = :paper_uuid
        """
    ), {"paper_uuid": paper_uuid}).mappings().all()
    suggested = _execute(db, text(
        """
        SELECT sr.id, sr.relation_key
        FROM suggested_relations sr
        JOIN suggestion_sets ss ON ss.id = sr.suggestion_set_id
        WHERE ss.paper_id = :paper_uuid
        """
    ), {"paper_uuid": paper_uuid}).mappings().all()

    def build(rows, key_name: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row in rows:
            db_id = _row_value(row["id"])
            mapping[db_id] = db_id
            key = _row_value(row[key_name])
            if key:
                mapping[key] = db_id
        return mapping

    return {
        "sentences": build(sentences, "sentence_key"),
        "paragraphs": build(paragraphs, "paragraph_key"),
        "mentions": build(mentions, "mention_key"),
        "suggested": build(suggested, "relation_key"),
    }


def _extract_manual_mention_ids(relation: RelationRecord, mention_map: dict[str, str]) -> tuple[str | None, str | None]:
    parts = relation.relation_id.split("_")
    if len(parts) >= 4 and parts[0] == "manual":
        subject_key = parts[2]
        object_key = "_".join(parts[3:])
        return mention_map.get(subject_key), mention_map.get(object_key)
    return None, None


def save_relations(db: Session, paper_id: str, relations: list[RelationRecord], editor_mode: str, current_user: UserProfile) -> str:
    del editor_mode
    from app.services import workflow_service

    paper = _paper_identity(db, paper_id)
    assignment = workflow_service.ensure_editable_assignment_for_paper(db, paper.uuid, current_user)
    assignment_id = assignment.id
    maps = _identity_maps_for_paper(db, paper.uuid)
    now = datetime.now(timezone.utc)
    try:
        workflow_service.mark_assignment_draft_saved(db, assignment_id)
        version = _execute(db, text(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM annotation_submissions
            WHERE assignment_id = :assignment_id
            """
        ), {"assignment_id": assignment_id}).scalar_one()
        submission_id = str(uuid4())
        _execute(db, text(
            """
            INSERT INTO annotation_submissions (id, assignment_id, version, status, created_at, submitted_at)
            VALUES (:id, :assignment_id, :version, 'draft', :now, NULL)
            """
        ), {"id": submission_id, "assignment_id": assignment_id, "version": int(version or 1), "now": now})

        json_expr = "CAST(:raw_payload AS JSONB)" if db.get_bind().dialect.name == "postgresql" else ":raw_payload"
        insert_relation_sql = text(f"""
            INSERT INTO annotation_submission_relations (
                id, submission_id, suggested_relation_id, action, sentence_id, support_paragraph_id,
                subject_mention_id, object_mention_id, subject_text, subject_type, predicate,
                object_text, object_type, confidence, accepted, evidence_text, relation_origin,
                inherited_from, raw_payload
            ) VALUES (
                :id, :submission_id, :suggested_relation_id, :action, :sentence_id, :support_paragraph_id,
                :subject_mention_id, :object_mention_id, :subject_text, :subject_type, :predicate,
                :object_text, :object_type, :confidence, :accepted, :evidence_text, :relation_origin,
                :inherited_from, {json_expr}
            )
        """)

        for relation in relations:
            relation_row_id = str(uuid4())
            suggested_relation_id = maps["suggested"].get(relation.relation_id)
            subject_mention_id, object_mention_id = _extract_manual_mention_ids(relation, maps["mentions"])
            sentence_id = maps["sentences"].get(relation.sentence_id) if relation.sentence_id else None
            paragraph_id = maps["paragraphs"].get(relation.support_paragraph_id) if relation.support_paragraph_id else None
            action = "add" if suggested_relation_id is None or relation.relation_id.startswith(("manual_", "custom_")) else "keep"
            _execute(db, insert_relation_sql, {
                "id": relation_row_id,
                "submission_id": submission_id,
                "suggested_relation_id": suggested_relation_id,
                "action": action,
                "sentence_id": sentence_id,
                "support_paragraph_id": paragraph_id,
                "subject_mention_id": subject_mention_id,
                "object_mention_id": object_mention_id,
                "subject_text": relation.subject_text,
                "subject_type": relation.subject_type,
                "predicate": relation.predicate,
                "object_text": relation.object_text,
                "object_type": relation.object_type,
                "confidence": relation.confidence,
                "accepted": relation.accepted,
                "evidence_text": relation.evidence_text,
                "relation_origin": relation.relation_origin,
                "inherited_from": relation.inherited_from,
                "raw_payload": json.dumps(relation.model_dump()),
            })

            support_keys = [item.strip() for item in relation.support_sentence_ids.split(";") if item.strip()]
            if not support_keys and relation.sentence_id:
                support_keys = [relation.sentence_id]
            for support_key in support_keys:
                support_uuid = maps["sentences"].get(support_key)
                if not support_uuid:
                    continue
                _execute(db, text(
                    """
                    INSERT INTO annotation_relation_support_sentences (submission_relation_id, sentence_id)
                    VALUES (:relation_id, :sentence_id)
                    """
                ), {"relation_id": relation_row_id, "sentence_id": support_uuid})

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _db_error(
            "Relations could not be saved to the platform database.",
            code="relation_save_failed",
            hint="Your unsaved work is still visible in the browser. Check annotation_submissions and annotation_submission_relations in Aiven, then save again.",
            paper_id=paper_id,
        ) from exc

    return f"postgresql://annotation_submissions/{submission_id}"
