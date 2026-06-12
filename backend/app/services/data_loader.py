from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from app import config


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    path: Path


DATASETS: dict[str, DatasetSpec] = {
    "raw": DatasetSpec("raw", "Raw candidates", config.RAW_RELATIONS_PATH),
}


RELATION_DEFAULTS = {
    "relation_id": "",
    "paper_id": "",
    "sentence_id": "",
    "paper_title": "",
    "doi": "",
    "subject_text": "",
    "subject_type": "",
    "predicate": "",
    "object_text": "",
    "object_type": "",
    "confidence": 1.0,
    "accepted": True,
    "evidence_text": "",
    "relation_origin": "",
    "inherited_from": "",
    "support_sentence_ids": "",
    "support_paragraph_id": "",
}


def list_datasets() -> list[DatasetSpec]:
    return list(DATASETS.values())



def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)



def normalize_relation_df(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    rename_map = {
        "candidate_id": "relation_id",
        "best_confidence": "confidence",
        "best_llm_confidence": "confidence",
        "representative_evidence": "evidence_text",
    }
    normalized = df.rename(columns=rename_map).copy()
    for column, value in RELATION_DEFAULTS.items():
        if column not in normalized.columns:
            normalized[column] = value if column != "relation_origin" else dataset
    normalized["confidence"] = pd.to_numeric(normalized["confidence"], errors="coerce").fillna(1.0)
    normalized["accepted"] = normalized["accepted"].fillna(True)
    for column in [
        "relation_id", "sentence_id", "paper_id", "paper_title", "doi", "subject_text", "subject_type",
        "predicate", "object_text", "object_type", "evidence_text", "relation_origin",
        "inherited_from", "support_sentence_ids", "support_paragraph_id",
    ]:
        normalized[column] = normalized[column].fillna("").astype(str)
    return normalized



def load_dataset_df(dataset: str) -> pd.DataFrame:
    if dataset not in DATASETS:
        dataset = "raw"
    spec = DATASETS[dataset]
    return normalize_relation_df(read_csv(spec.path), dataset)


def dataset_slug(dataset: str) -> str:
    return "relations"


def edited_paper_dir(dataset: str, paper_id: str) -> Path:
    return config.EDITED_DIR / paper_id


def edited_latest_file_path(dataset: str, paper_id: str) -> Path:
    return edited_paper_dir(dataset, paper_id) / "latest.csv"


def edited_snapshot_path(dataset: str, paper_id: str, editor_mode: str, relation_count: int) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return edited_paper_dir(dataset, paper_id) / f"{timestamp}__{editor_mode}__{relation_count}_relations.csv"


def legacy_edited_file_path(dataset: str, paper_id: str) -> Path:
    return config.EDITED_DIR / f"{paper_id}_edited_graph.csv"



def load_edited_dataset_df(dataset: str, paper_id: str) -> pd.DataFrame:
    candidate_paths = [
        edited_latest_file_path(dataset, paper_id),
        legacy_edited_file_path(dataset, paper_id),
    ]
    existing_paths = [path for path in candidate_paths if path.exists()]
    if not existing_paths:
        return normalize_relation_df(pd.DataFrame(), dataset)
    path = max(existing_paths, key=lambda item: item.stat().st_mtime)
    return normalize_relation_df(read_csv(path), dataset)



def edited_file_path(dataset: str, paper_id: str) -> Path:
    return edited_latest_file_path(dataset, paper_id)



def load_paper_index() -> pd.DataFrame:
    df = read_csv(config.PAPER_INDEX_PATH)
    if "title" in df.columns and "paper_title" not in df.columns:
        df["paper_title"] = df["title"]
    return df



def load_sentence_index() -> pd.DataFrame:
    return read_csv(config.SENTENCE_INDEX_PATH)



def load_entity_mentions() -> pd.DataFrame:
    df = read_csv(config.ENTITY_MENTIONS_PATH)
    for column in ["mention_id", "sentence_id", "paper_id", "text", "schema_type", "ner_label"]:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").astype(str)
    for column in ["token_start", "token_end"]:
        if column not in df.columns:
            df[column] = None
    return df



def load_schema_predicates() -> list[str]:
    df = read_csv(config.SCHEMA_RELATIONS_PATH)
    if "predicate" not in df.columns:
        base_predicates: list[str] = []
    else:
        base_predicates = df["predicate"].dropna().astype(str).unique().tolist()
    return sorted(set(base_predicates) | set(load_custom_schema_predicates()))


def load_direct_schema_predicates() -> list[str]:
    df = read_csv(config.SCHEMA_RELATIONS_PATH)
    if "predicate" not in df.columns:
        direct_predicates: list[str] = []
    else:
        if "is_bridged" in df.columns:
            direct_df = df[df["is_bridged"].fillna("").astype(str).str.strip().str.casefold() != "inherited"].copy()
        elif "inherited_from" in df.columns:
            direct_df = df[df["inherited_from"].fillna("").astype(str).str.strip().eq("")].copy()
        else:
            direct_df = df

        direct_predicates = direct_df["predicate"].dropna().astype(str).unique().tolist()

    return sorted(set(direct_predicates) | set(load_custom_schema_predicates()))


def load_custom_schema_predicates() -> list[str]:
    df = read_csv(config.CUSTOM_SCHEMA_PREDICATES_PATH)
    if "predicate" not in df.columns:
        return []
    return sorted(df["predicate"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist())


def save_custom_schema_predicate(predicate: str) -> list[str]:
    cleaned = predicate.strip()
    if not cleaned:
        return load_direct_schema_predicates()

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = read_csv(config.CUSTOM_SCHEMA_PREDICATES_PATH)
    if "predicate" not in existing.columns:
        existing = pd.DataFrame(columns=["predicate", "created_at"])

    normalized_existing = existing["predicate"].fillna("").astype(str).str.strip().tolist()
    if cleaned not in normalized_existing:
        updated = pd.concat(
            [
                existing,
                pd.DataFrame([{"predicate": cleaned, "created_at": datetime.now().isoformat(timespec="seconds")}]),
            ],
            ignore_index=True,
        )
        updated.to_csv(config.CUSTOM_SCHEMA_PREDICATES_PATH, index=False)

    return load_direct_schema_predicates()
