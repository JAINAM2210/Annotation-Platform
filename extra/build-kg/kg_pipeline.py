from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from kg_schema import (
    DEFAULT_PAPER_MAPPING_CSV,
    DEFAULT_RELATIONS_CSV,
    DEFAULT_TYPE_MAPPING_JSON,
    KgSchema,
    PaperRecord,
    load_paper_records,
    load_schema,
    load_type_mapping,
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_TEXT_DIR = DATA_DIR / "txt_files"
DEFAULT_BIO_DIR = DATA_DIR / "bio_extracted_entites_txts"
DEFAULT_OUTPUT_DIR = DATA_DIR


@dataclass(frozen=True)
class SentenceRecord:
    sentence_id: str
    paper_id: str
    sentence_index: int
    paper_title: str
    doi: str
    source_text_path: str | None
    source_bio_path: str
    text: str


@dataclass(frozen=True)
class MentionRecord:
    mention_id: str
    sentence_id: str
    paper_id: str
    paper_title: str
    doi: str
    text: str
    ner_label: str
    schema_type: str | None
    token_start: int
    token_end: int


@dataclass(frozen=True)
class RelationCandidate:
    candidate_id: str
    sentence_id: str
    paper_id: str
    paper_title: str
    doi: str
    subject_mention_id: str
    subject_text: str
    subject_type: str
    predicate: str
    object_mention_id: str
    object_text: str
    object_type: str
    evidence_text: str
    relation_origin: str
    inherited_from: str | None


def detokenize(tokens: list[str]) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    text = re.sub(r"\s+([\)\]\}])", r"\1", text)
    text = re.sub(r"\s+'", "'", text)
    text = re.sub(r"'\s+", "'", text)
    text = re.sub(r"\s+-\s+", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def iter_bio_sentences(path: Path):
    with path.open(encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        if not header or header[0] != "TOKEN":
            raise ValueError(f"Unexpected BIO header in {path}")

        rows: list[list[str]] = []
        for line in handle:
            stripped = line.rstrip("\n")
            if not stripped:
                if rows:
                    yield header, rows
                    rows = []
                continue

            parts = stripped.split("\t")
            if len(parts) != len(header):
                raise ValueError(
                    f"Malformed BIO row in {path}: expected {len(header)} columns, got {len(parts)}"
                )
            rows.append(parts)

        if rows:
            yield header, rows


def _flush_span(
    mentions: list[MentionRecord],
    *,
    sentence: SentenceRecord,
    mention_counter: int,
    label_name: str,
    schema_type: str | None,
    tokens: list[str],
    start_index: int,
    end_index: int,
) -> int:
    mention_counter += 1
    mentions.append(
        MentionRecord(
            mention_id=f"{sentence.sentence_id}:m{mention_counter:03d}",
            sentence_id=sentence.sentence_id,
            paper_id=sentence.paper_id,
            paper_title=sentence.paper_title,
            doi=sentence.doi,
            text=detokenize(tokens[start_index : end_index + 1]),
            ner_label=label_name,
            schema_type=schema_type,
            token_start=start_index,
            token_end=end_index,
        )
    )
    return mention_counter


def extract_sentences_and_mentions(
    papers: list[PaperRecord],
    type_mapping: dict[str, str | None],
) -> tuple[list[SentenceRecord], list[MentionRecord]]:
    sentences: list[SentenceRecord] = []
    mentions: list[MentionRecord] = []

    for paper in papers:
        if not paper.bio_path:
            continue

        bio_path = Path(paper.bio_path)
        for sentence_index, (header, rows) in enumerate(iter_bio_sentences(bio_path), start=1):
            tokens = [row[0] for row in rows]
            sentence = SentenceRecord(
                sentence_id=f"{paper.paper_id}:s{sentence_index:04d}",
                paper_id=paper.paper_id,
                sentence_index=sentence_index,
                paper_title=paper.title,
                doi=paper.doi,
                source_text_path=paper.text_path,
                source_bio_path=str(bio_path),
                text=detokenize(tokens),
            )
            sentences.append(sentence)

            mention_counter = 0
            for column_index, label_name in enumerate(header[1:], start=1):
                schema_type = type_mapping.get(label_name)
                span_start: int | None = None

                for token_index, row in enumerate(rows):
                    tag = row[column_index]
                    if tag.startswith("B-"):
                        if span_start is not None:
                            mention_counter = _flush_span(
                                mentions,
                                sentence=sentence,
                                mention_counter=mention_counter,
                                label_name=label_name,
                                schema_type=schema_type,
                                tokens=tokens,
                                start_index=span_start,
                                end_index=token_index - 1,
                            )
                        span_start = token_index
                    elif tag.startswith("I-"):
                        if span_start is None:
                            span_start = token_index
                    else:
                        if span_start is not None:
                            mention_counter = _flush_span(
                                mentions,
                                sentence=sentence,
                                mention_counter=mention_counter,
                                label_name=label_name,
                                schema_type=schema_type,
                                tokens=tokens,
                                start_index=span_start,
                                end_index=token_index - 1,
                            )
                            span_start = None

                if span_start is not None:
                    mention_counter = _flush_span(
                        mentions,
                        sentence=sentence,
                        mention_counter=mention_counter,
                        label_name=label_name,
                        schema_type=schema_type,
                        tokens=tokens,
                        start_index=span_start,
                        end_index=len(tokens) - 1,
                    )

    return sentences, mentions


def build_relation_candidates(
    schema: KgSchema,
    sentences: list[SentenceRecord],
    mentions: list[MentionRecord],
) -> list[RelationCandidate]:
    sentence_lookup = {sentence.sentence_id: sentence for sentence in sentences}
    mentions_by_sentence: dict[str, list[MentionRecord]] = defaultdict(list)
    for mention in mentions:
        if mention.schema_type:
            mentions_by_sentence[mention.sentence_id].append(mention)

    candidates: list[RelationCandidate] = []
    candidate_counter = 0
    seen: set[tuple[str, str, str]] = set()

    for sentence_id, sentence_mentions in mentions_by_sentence.items():
        sentence = sentence_lookup[sentence_id]
        for subject in sentence_mentions:
            for obj in sentence_mentions:
                if subject.mention_id == obj.mention_id:
                    continue
                rule = schema.rule_for_pair(subject.schema_type, obj.schema_type)
                if not rule:
                    continue
                key = (subject.mention_id, rule.predicate, obj.mention_id)
                if key in seen:
                    continue
                seen.add(key)
                candidate_counter += 1
                candidates.append(
                    RelationCandidate(
                        candidate_id=f"cand_{candidate_counter:06d}",
                        sentence_id=sentence_id,
                        paper_id=sentence.paper_id,
                        paper_title=sentence.paper_title,
                        doi=sentence.doi,
                        subject_mention_id=subject.mention_id,
                        subject_text=subject.text,
                        subject_type=subject.schema_type,
                        predicate=rule.predicate,
                        object_mention_id=obj.mention_id,
                        object_text=obj.text,
                        object_type=obj.schema_type,
                        evidence_text=sentence.text,
                        relation_origin=rule.is_bridged or "direct",
                        inherited_from=rule.inherited_from,
                    )
                )

    return candidates


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def compute_dataset() -> tuple[
    KgSchema,
    dict[str, str | None],
    list[PaperRecord],
    list[SentenceRecord],
    list[MentionRecord],
    list[RelationCandidate],
    dict[str, object],
]:
    schema = load_schema(DATA_DIR / DEFAULT_RELATIONS_CSV)
    type_mapping = load_type_mapping(DATA_DIR / DEFAULT_TYPE_MAPPING_JSON, schema)
    papers = load_paper_records(
        DATA_DIR / DEFAULT_PAPER_MAPPING_CSV,
        text_dir=DEFAULT_TEXT_DIR,
        bio_dir=DEFAULT_BIO_DIR,
    )
    sentences, mentions = extract_sentences_and_mentions(papers, type_mapping)
    candidates = build_relation_candidates(schema, sentences, mentions)
    schema_summary = schema.summary()
    schema_summary["paper_count"] = len(papers)
    schema_summary["papers_with_text"] = sum(1 for paper in papers if paper.text_path)
    schema_summary["papers_with_bio"] = sum(1 for paper in papers if paper.bio_path)
    schema_summary["sentence_count"] = len(sentences)
    schema_summary["mention_count"] = len(mentions)
    schema_summary["mapped_mention_count"] = sum(1 for mention in mentions if mention.schema_type)
    schema_summary["relation_candidate_count"] = len(candidates)
    schema_summary["unmapped_ner_labels"] = sorted(
        label for label, schema_type in type_mapping.items() if schema_type is None
    )

    return schema, type_mapping, papers, sentences, mentions, candidates, schema_summary


def build_outputs(
    output_dir: Path,
    *,
    papers: list[PaperRecord],
    sentences: list[SentenceRecord],
    mentions: list[MentionRecord],
    candidates: list[RelationCandidate],
    schema_summary: dict[str, object],
) -> dict[str, object]:

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "schema_summary.json").write_text(
        json.dumps(schema_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_csv(output_dir / "paper_index.csv", [asdict(paper) for paper in papers])
    write_csv(output_dir / "sentence_index.csv", [asdict(sentence) for sentence in sentences])
    write_csv(output_dir / "entity_mentions.csv", [asdict(mention) for mention in mentions])
    write_csv(
        output_dir / "relation_candidates.csv",
        [asdict(candidate) for candidate in candidates],
    )

    return schema_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the first-pass KG foundation from Annotation_Platform/data inputs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for KG CSV and JSON artifacts. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print the current schema and corpus summary without writing output files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _, _, papers, sentences, mentions, candidates, summary = compute_dataset()

    if args.summary_only:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    written_summary = build_outputs(
        args.output_dir,
        papers=papers,
        sentences=sentences,
        mentions=mentions,
        candidates=candidates,
        schema_summary=summary,
    )
    print(json.dumps(written_summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
