from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_INPUT = DATA_DIR / "validated" / "validated_relation_candidates.csv"
DEFAULT_OUTPUT_DIR = DATA_DIR / "llm_verified"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
DEFAULT_THRESHOLD = 0.65
DEFAULT_MAX_ROWS = 250
TOGETHER_ENDPOINT = "https://api.together.xyz/v1/chat/completions"

try:
    from together import Together
except ImportError:  # pragma: no cover - optional dependency
    Together = None


SYSTEM_PROMPT = """You verify scientific knowledge-graph relations.

You are given:
- a candidate subject entity and its type
- a predicate from a fixed ontology
- a candidate object entity and its type
- an evidence sentence
- nearby context

Your job is to decide whether the context supports the exact relation.

Rules:
- Be conservative.
- Accept only if the relation is explicitly or very strongly implied.
- Reject if the entities merely co-occur without expressing the relation.
- Reject if the types or roles seem mismatched.
- Use the ontology predicate literally, not loosely.
- If uncertain, return "uncertain".

Return JSON only with this exact schema:
{
  "decision": "supported" | "unsupported" | "uncertain",
  "confidence": 0.0,
  "rationale": "short explanation",
  "evidence_span": "short supporting text or empty string"
}
"""


@dataclass(frozen=True)
class LlmVerifiedCandidate:
    candidate_id: str
    paper_id: str
    paper_title: str
    doi: str
    sentence_id: str
    subject_text: str
    subject_type: str
    predicate: str
    object_text: str
    object_type: str
    heuristic_confidence: float
    heuristic_accepted: bool
    llm_decision: str
    llm_confidence: float
    final_accepted: bool
    rationale: str
    evidence_span: str
    evidence_text: str
    context_text: str
    api_error: str


@dataclass(frozen=True)
class LlmVerifiedRelation:
    relation_id: str
    paper_id: str
    paper_title: str
    doi: str
    subject_text: str
    subject_type: str
    predicate: str
    object_text: str
    object_type: str
    best_llm_confidence: float
    support_count: int
    llm_decision: str
    representative_evidence: str
    rationale: str


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_user_prompt(row: dict[str, str]) -> str:
    heuristic_conf = row.get("confidence", "")
    heuristic_accepted = row.get("accepted", "")
    return f"""Candidate relation:

Subject: {row['subject_text']}
Subject type: {row['subject_type']}
Predicate: {row['predicate']}
Object: {row['object_text']}
Object type: {row['object_type']}

Heuristic validator:
- confidence: {heuristic_conf}
- accepted: {heuristic_accepted}

Evidence sentence:
{row['evidence_text']}

Nearby context:
{row['context_text']}

Decide whether the predicate is actually supported between the subject and object.
Return JSON only.
"""


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def parse_llm_json(text: str) -> dict[str, object]:
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def call_together(
    *,
    api_key: str,
    model: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 250,
) -> dict[str, object]:
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    request = urllib.request.Request(
        TOGETHER_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    parsed = parse_llm_json(content)
    return parsed


def call_together_sdk(
    *,
    api_key: str,
    model: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 250,
) -> dict[str, object]:
    if Together is None:
        raise RuntimeError("Together SDK is not installed in this environment.")

    client = Together(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = response.choices[0].message.content
    return parse_llm_json(content)


def safe_llm_decision(parsed: dict[str, object]) -> tuple[str, float, str, str]:
    decision = str(parsed.get("decision", "uncertain")).strip().lower()
    if decision not in {"supported", "unsupported", "uncertain"}:
        decision = "uncertain"

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    rationale = str(parsed.get("rationale", "")).strip()
    evidence_span = str(parsed.get("evidence_span", "")).strip()
    return decision, confidence, rationale, evidence_span


def verify_rows(
    rows: list[dict[str, str]],
    *,
    api_key: str,
    model: str,
    threshold: float,
    sleep_seconds: float,
    fail_on_api_error: bool,
    api_mode: str,
) -> list[LlmVerifiedCandidate]:
    verified: list[LlmVerifiedCandidate] = []

    for index, row in enumerate(rows, start=1):
        prompt = build_user_prompt(row)
        api_error = ""
        try:
            if api_mode == "sdk":
                parsed = call_together_sdk(api_key=api_key, model=model, user_prompt=prompt)
            else:
                parsed = call_together(api_key=api_key, model=model, user_prompt=prompt)
            decision, llm_confidence, rationale, evidence_span = safe_llm_decision(parsed)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            api_error = f"HTTP {exc.code}: {body or exc.reason}"
            if fail_on_api_error and exc.code in {401, 403, 404, 429}:
                raise RuntimeError(
                    f"Together API request failed for candidate {row['candidate_id']} with HTTP {exc.code}. "
                    f"Response: {body or exc.reason}"
                ) from exc
            decision = "uncertain"
            llm_confidence = 0.0
            rationale = f"LLM call failed: HTTP {exc.code}"
            evidence_span = ""
        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
            api_error = str(exc)
            if fail_on_api_error:
                raise RuntimeError(
                    f"Together API request failed for candidate {row['candidate_id']}: {exc}"
                ) from exc
            decision = "uncertain"
            llm_confidence = 0.0
            rationale = f"LLM call failed: {exc}"
            evidence_span = ""

        heuristic_confidence = float(row.get("confidence") or 0.0)
        heuristic_accepted = str(row.get("accepted", "")).strip().lower() == "true"
        final_accepted = decision == "supported" and llm_confidence >= threshold

        verified.append(
            LlmVerifiedCandidate(
                candidate_id=row["candidate_id"],
                paper_id=row["paper_id"],
                paper_title=row["paper_title"],
                doi=row["doi"],
                sentence_id=row["sentence_id"],
                subject_text=row["subject_text"],
                subject_type=row["subject_type"],
                predicate=row["predicate"],
                object_text=row["object_text"],
                object_type=row["object_type"],
                heuristic_confidence=heuristic_confidence,
                heuristic_accepted=heuristic_accepted,
                llm_decision=decision,
                llm_confidence=llm_confidence,
                final_accepted=final_accepted,
                rationale=rationale,
                evidence_span=evidence_span,
                evidence_text=row["evidence_text"],
                context_text=row["context_text"],
                api_error=api_error,
            )
        )

        if sleep_seconds:
            time.sleep(sleep_seconds)

    return verified


def consolidate_relations(rows: list[LlmVerifiedCandidate]) -> list[LlmVerifiedRelation]:
    grouped: dict[tuple[str, str, str, str, str, str], list[LlmVerifiedCandidate]] = defaultdict(list)
    for row in rows:
        if not row.final_accepted:
            continue
        key = (
            row.paper_id,
            row.subject_text,
            row.subject_type,
            row.predicate,
            row.object_text,
            row.object_type,
        )
        grouped[key].append(row)

    consolidated: list[LlmVerifiedRelation] = []
    for index, candidates in enumerate(grouped.values(), start=1):
        best = max(candidates, key=lambda item: item.llm_confidence)
        consolidated.append(
            LlmVerifiedRelation(
                relation_id=f"llm_rel_{index:06d}",
                paper_id=best.paper_id,
                paper_title=best.paper_title,
                doi=best.doi,
                subject_text=best.subject_text,
                subject_type=best.subject_type,
                predicate=best.predicate,
                object_text=best.object_text,
                object_type=best.object_type,
                best_llm_confidence=best.llm_confidence,
                support_count=len(candidates),
                llm_decision=best.llm_decision,
                representative_evidence=best.evidence_text,
                rationale=best.rationale,
            )
        )
    return consolidated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify validated KG relation candidates with a Together-hosted LLM."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input validated candidate CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for LLM verification artifacts. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Together model to use. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"LLM support threshold for acceptance. Default: {DEFAULT_THRESHOLD}",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=DEFAULT_MAX_ROWS,
        help=f"Maximum rows to send to the LLM in one run. Default: {DEFAULT_MAX_ROWS}",
    )
    parser.add_argument(
        "--all-rows",
        action="store_true",
        help="Verify every input row instead of capping at --max-rows.",
    )
    parser.add_argument(
        "--include-rejected-heuristic",
        action="store_true",
        help="Also send heuristic-rejected candidates to the LLM. By default only heuristic-accepted rows are verified.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay between API calls. Default: 0.0",
    )
    parser.add_argument(
        "--api-mode",
        choices=["sdk", "http"],
        default="sdk" if Together is not None else "http",
        help="Choose Together SDK mode or raw HTTP mode. Default prefers SDK when available.",
    )
    parser.add_argument(
        "--no-fail-on-api-error",
        action="store_true",
        help="Do not stop on Together API errors; mark affected rows as uncertain instead.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise SystemExit("TOGETHER_API_KEY is not set in the environment.")

    rows = load_csv(args.input_csv)
    if not args.include_rejected_heuristic:
        rows = [row for row in rows if str(row.get("accepted", "")).strip().lower() == "true"]
    if not args.all_rows:
        rows = rows[: args.max_rows]

    verified = verify_rows(
        rows,
        api_key=api_key,
        model=args.model,
        threshold=args.threshold,
        sleep_seconds=args.sleep_seconds,
        fail_on_api_error=not args.no_fail_on_api_error,
        api_mode=args.api_mode,
    )
    consolidated = consolidate_relations(verified)

    api_errors = [row.api_error for row in verified if row.api_error]
    summary = {
        "input_row_count": len(rows),
        "llm_supported_count": sum(1 for row in verified if row.llm_decision == "supported"),
        "llm_unsupported_count": sum(1 for row in verified if row.llm_decision == "unsupported"),
        "llm_uncertain_count": sum(1 for row in verified if row.llm_decision == "uncertain"),
        "final_accepted_count": sum(1 for row in verified if row.final_accepted),
        "final_relation_count": len(consolidated),
        "threshold": args.threshold,
        "model": args.model,
        "api_mode": args.api_mode,
        "api_error_count": len(api_errors),
        "api_error_examples": api_errors[:5],
        "top_supported_predicates": Counter(
            row.predicate for row in verified if row.final_accepted
        ).most_common(15),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "llm_verified_candidates.csv",
        [asdict(row) for row in verified],
    )
    write_csv(
        args.output_dir / "llm_verified_relations.csv",
        [asdict(row) for row in consolidated],
    )
    (args.output_dir / "llm_verification_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
