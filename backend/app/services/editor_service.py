from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from app import config
from app.services.data_loader import (
    edited_file_path,
    edited_latest_file_path,
    edited_paper_dir,
    edited_snapshot_path,
    load_dataset_df,
    load_edited_dataset_df,
    load_entity_mentions,
    load_paper_index,
    load_sentence_index,
)


def dataset_label(dataset: str) -> str:
    return "raw"



def has_edited_version(dataset: str, paper_id: str) -> bool:
    return edited_file_path(dataset, paper_id).exists()



def paper_relations(dataset: str, paper_id: str) -> tuple[pd.DataFrame, str]:
    edited_df = load_edited_dataset_df(dataset, paper_id)
    if not edited_df.empty:
        edited_df = edited_df[edited_df["paper_id"] == paper_id].copy().reset_index(drop=True)
        if not edited_df.empty and edited_df["relation_origin"].eq("manual_edit").all():
            source_df = load_dataset_df(dataset)
            source_df = source_df[source_df["paper_id"] == paper_id].copy().reset_index(drop=True)
            merged_df = pd.concat([source_df, edited_df], ignore_index=True)
            return merged_df, "edited + source"
        return edited_df, "edited"
    df = load_dataset_df(dataset)
    return df[df["paper_id"] == paper_id].copy().reset_index(drop=True), "source"



def paper_sentences(paper_id: str) -> pd.DataFrame:
    df = load_sentence_index()
    return df[df["paper_id"] == paper_id].copy().sort_values("sentence_index").reset_index(drop=True)



def paper_mentions(paper_id: str) -> pd.DataFrame:
    df = load_entity_mentions()
    return df[df["paper_id"] == paper_id].copy().sort_values(["sentence_id", "token_start"]).reset_index(drop=True)


def _normalize_for_match(value: str) -> str:
    compact = value.lower()
    compact = re.sub(r"\s+", " ", compact).strip()
    compact = re.sub(r"\s*([,.;:!?()\[\]{}])\s*", r"\1", compact)
    compact = re.sub(r"[^0-9a-z]+", "", compact)
    return compact


def _normalize_for_display(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _compatible_prefix(candidate: str, target: str) -> bool:
    if not candidate or not target:
        return False
    if target.startswith(candidate):
        return True

    if len(candidate) > len(target):
        overflow = len(candidate) - len(target)
        if overflow > 8:
            return False
        comparison_window = candidate[: len(target)]
        return SequenceMatcher(None, comparison_window, target).ratio() >= 0.995

    comparison_window = target[: len(candidate)]
    if not comparison_window or len(candidate) < 32:
        return False

    ratio = SequenceMatcher(None, candidate, comparison_window).ratio()
    return ratio >= 0.98


def _raw_paragraphs(source_text: str) -> list[str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n+", source_text)
        if paragraph.strip()
    ]
    merged: list[str] = []
    pending_heading_parts: list[str] = []

    for paragraph in paragraphs:
        is_heading_only = not re.search(r"[.!?]", paragraph)
        if is_heading_only:
            pending_heading_parts.append(paragraph)
            continue

        if pending_heading_parts:
            merged.append(" ".join([*pending_heading_parts, paragraph]))
            pending_heading_parts = []
        else:
            merged.append(paragraph)

    if pending_heading_parts:
        merged.extend(pending_heading_parts)

    stitched: list[str] = []
    for paragraph in merged:
        normalized = paragraph.strip()
        if not stitched:
            stitched.append(normalized)
            continue

        previous = stitched[-1]
        previous_ends_mid_sentence = not re.search(r'[.!?]["\')\]]*\s*$', previous)
        current_looks_like_continuation = bool(re.match(r'^[a-z0-9(\[]', normalized))

        if previous_ends_mid_sentence or current_looks_like_continuation:
            stitched[-1] = f"{previous} {normalized}"
        else:
            stitched.append(normalized)

    return stitched


def paper_paragraphs(paper_id: str) -> list[dict[str, object]]:
    sentence_df = paper_sentences(paper_id)
    if sentence_df.empty:
        return []

    source_path_value = sentence_df.iloc[0].get("source_text_path", "")
    source_path = Path(str(source_path_value)) if pd.notna(source_path_value) and str(source_path_value).strip() else None

    if source_path and source_path.exists():
        source_text = source_path.read_text(encoding="utf-8")
        candidate_paragraphs = _raw_paragraphs(source_text)
    else:
        candidate_paragraphs = sentence_df["text"].astype(str).tolist()

    sentences = sentence_df.to_dict("records")
    sentence_cursor = 0
    paragraphs: list[dict[str, object]] = []

    for paragraph_text in candidate_paragraphs:
        paragraph_display = _normalize_for_display(paragraph_text)
        paragraph_normalized = _normalize_for_match(paragraph_text)
        paragraph_reconstructed = ""
        sentence_ids: list[str] = []

        while sentence_cursor < len(sentences):
            sentence = sentences[sentence_cursor]
            sentence_text = _normalize_for_match(str(sentence["text"]))
            next_reconstructed = paragraph_reconstructed + sentence_text

            if not _compatible_prefix(next_reconstructed, paragraph_normalized):
                break

            sentence_ids.append(str(sentence["sentence_id"]))
            paragraph_reconstructed = next_reconstructed
            sentence_cursor += 1

            if paragraph_reconstructed == paragraph_normalized:
                break

        if sentence_ids:
            paragraphs.append({
                "paragraph_id": f"{paper_id}:p{len(paragraphs) + 1:04d}",
                "paper_id": paper_id,
                "paragraph_index": len(paragraphs) + 1,
                "text": paragraph_display,
                "sentence_ids": sentence_ids,
            })

    while sentence_cursor < len(sentences):
        sentence = sentences[sentence_cursor]
        paragraphs.append({
            "paragraph_id": f"{paper_id}:p{len(paragraphs) + 1:04d}",
            "paper_id": paper_id,
            "paragraph_index": len(paragraphs) + 1,
            "text": str(sentence["text"]).strip(),
            "sentence_ids": [str(sentence["sentence_id"])],
        })
        sentence_cursor += 1

    return paragraphs



def paper_summary(dataset: str, paper_id: str) -> dict[str, str | bool]:
    df = load_paper_index()
    row = df[df["paper_id"] == paper_id].head(1)
    if row.empty:
        return {"paper_id": paper_id, "title": "", "doi": "", "has_edited_version": False}
    item = row.iloc[0]
    return {
        "paper_id": str(item["paper_id"]),
        "title": str(item.get("paper_title", item.get("title", ""))),
        "doi": str(item.get("doi", "")),
        "has_edited_version": has_edited_version(dataset, paper_id),
    }



def save_relations(dataset: str, paper_id: str, relations_df: pd.DataFrame, editor_mode: str) -> Path:
    config.EDITED_DIR.mkdir(parents=True, exist_ok=True)
    paper_dir = edited_paper_dir(dataset, paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    if "support_paragraph_id" not in relations_df.columns:
        relations_df["support_paragraph_id"] = ""

    if editor_mode == "paragraph" and not relations_df.empty:
        sentence_to_paragraph = {
            sentence_id: paragraph["paragraph_id"]
            for paragraph in paper_paragraphs(paper_id)
            for sentence_id in paragraph["sentence_ids"]
        }

        def infer_paragraph_id(row: pd.Series) -> str:
            existing = str(row.get("support_paragraph_id", "")).strip()
            if existing:
                return existing
            sentence_ids = str(row.get("support_sentence_ids", "")).split(";")
            if not any(sentence_ids):
                sentence_ids = [str(row.get("sentence_id", ""))]
            for sentence_id in sentence_ids:
                paragraph_id = sentence_to_paragraph.get(sentence_id.strip())
                if paragraph_id:
                    return str(paragraph_id)
            return ""

        relations_df["support_paragraph_id"] = relations_df.apply(infer_paragraph_id, axis=1)

    if not relations_df.empty and "relation_id" in relations_df.columns:
        custom_rows = relations_df["relation_id"].fillna("").astype(str).str.startswith("custom_")
        empty_columns = [
            "sentence_id",
            "subject_mention_id",
            "object_mention_id",
            "evidence_text",
            "relation_origin",
            "inherited_from",
            "confidence",
            "accepted",
            "support_sentence_ids",
        ]
        for column in empty_columns:
            if column in relations_df.columns:
                relations_df.loc[custom_rows, column] = ""
        if "subject_type" in relations_df.columns:
            relations_df.loc[custom_rows, "subject_type"] = "custom"
        if "object_type" in relations_df.columns:
            relations_df.loc[custom_rows, "object_type"] = "custom"

    snapshot_path = edited_snapshot_path(dataset, paper_id, editor_mode, len(relations_df.index))
    latest_path = edited_latest_file_path(dataset, paper_id)
    relations_df.to_csv(snapshot_path, index=False)
    relations_df.to_csv(latest_path, index=False)
    return snapshot_path
