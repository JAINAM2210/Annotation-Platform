from __future__ import annotations

import csv
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_RELATIONS_CSV = "relations.csv"
DEFAULT_PAPER_MAPPING_CSV = "paper_doi_citation_mapping.csv"
DEFAULT_TYPE_MAPPING_JSON = "ner_to_schema_type_map.json"


def normalize_lookup_key(value: str) -> str:
    text = Path(value).stem
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("_", " ")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return re.sub(r"[^0-9a-z]+", "", text)


@dataclass(frozen=True)
class RelationRule:
    subject_type: str
    predicate: str
    object_type: str
    is_bridged: str | None = None
    inherited_from: str | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.subject_type, self.predicate, self.object_type)


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    doi: str
    citation: str
    text_path: str | None = None
    bio_path: str | None = None


class KgSchema:
    def __init__(self, rules: list[RelationRule]):
        self.rules = rules
        self.allowed_types = sorted(
            {rule.subject_type for rule in rules} | {rule.object_type for rule in rules}
        )
        self.allowed_predicates = sorted({rule.predicate for rule in rules})
        self.rules_by_pair = {
            (rule.subject_type, rule.object_type): rule for rule in rules
        }
        self.rules_by_triple = {rule.key: rule for rule in rules}

    def rule_for_pair(self, subject_type: str, object_type: str) -> RelationRule | None:
        return self.rules_by_pair.get((subject_type, object_type))

    def predicate_for_pair(self, subject_type: str, object_type: str) -> str | None:
        rule = self.rule_for_pair(subject_type, object_type)
        return rule.predicate if rule else None

    def allows(self, subject_type: str, predicate: str, object_type: str) -> bool:
        return (subject_type, predicate, object_type) in self.rules_by_triple

    def summary(self) -> dict[str, Any]:
        inherited = sum(1 for rule in self.rules if rule.is_bridged == "inherited")
        direct = len(self.rules) - inherited
        return {
            "rule_count": len(self.rules),
            "direct_rule_count": direct,
            "inherited_rule_count": inherited,
            "allowed_types": self.allowed_types,
            "allowed_predicates": self.allowed_predicates,
        }


def load_relation_rules(path: str | Path) -> list[RelationRule]:
    rows: list[RelationRule] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(
                RelationRule(
                    subject_type=raw["subject"].strip(),
                    predicate=raw["predicate"].strip(),
                    object_type=raw["object"].strip(),
                    is_bridged=(raw.get("is_bridged") or "").strip() or None,
                    inherited_from=(raw.get("inherited_from") or "").strip() or None,
                )
            )
    return rows


def load_schema(path: str | Path) -> KgSchema:
    return KgSchema(load_relation_rules(path))


def load_type_mapping(path: str | Path, schema: KgSchema) -> dict[str, str | None]:
    with Path(path).open(encoding="utf-8") as handle:
        mapping = json.load(handle)

    invalid = {
        label: schema_type
        for label, schema_type in mapping.items()
        if schema_type is not None and schema_type not in schema.allowed_types
    }
    if invalid:
        details = ", ".join(f"{label} -> {value}" for label, value in sorted(invalid.items()))
        raise ValueError(f"Type mapping contains unknown schema types: {details}")

    return mapping


def _build_file_lookup(directory: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    for path in sorted(directory.glob("*.txt")):
        lookup[normalize_lookup_key(path.stem)] = path
    return lookup


def _resolve_lookup_path(lookup: dict[str, Path], key: str) -> str | None:
    if key in lookup:
        return str(lookup[key])

    matches = difflib.get_close_matches(key, lookup.keys(), n=1, cutoff=0.94)
    if not matches:
        return None

    return str(lookup[matches[0]])


def load_paper_records(
    mapping_csv: str | Path,
    text_dir: str | Path | None = None,
    bio_dir: str | Path | None = None,
) -> list[PaperRecord]:
    text_lookup = _build_file_lookup(Path(text_dir)) if text_dir else {}
    bio_lookup = _build_file_lookup(Path(bio_dir)) if bio_dir else {}

    records: list[PaperRecord] = []
    with Path(mapping_csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader, start=1):
            key = normalize_lookup_key(raw["Title"])
            text_path = _resolve_lookup_path(text_lookup, key) if text_lookup else None
            bio_path = _resolve_lookup_path(bio_lookup, key) if bio_lookup else None
            records.append(
                PaperRecord(
                    paper_id=f"paper_{index:03d}",
                    title=raw["Title"].strip(),
                    doi=raw["DOI"].strip(),
                    citation=raw["Citation"].strip(),
                    text_path=text_path,
                    bio_path=bio_path,
                )
            )
    return records
