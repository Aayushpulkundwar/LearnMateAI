"""Versioned, human-reviewable RAG evaluation datasets and CLI helpers."""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


SPLITS = {"dev", "validation", "test"}
CLAIM_LABELS = {"supported", "contradicted", "insufficiently_evidenced"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def load_review_dataset(path: str | Path) -> list[dict]:
    source = Path(path)
    return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_review_dataset(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return all structural/integrity errors without mutating reviewer data."""
    errors, ids, questions = [], set(), {}
    for index, record in enumerate(records):
        prefix = f"record {index}"
        required = ("schema_version", "id", "split", "question", "document_id", "answerable", "gold_passage_ids", "reference_answer", "evidence_spans", "claims")
        missing = [name for name in required if name not in record]
        if missing:
            errors.append(f"{prefix}: missing {', '.join(missing)}")
            continue
        if record["schema_version"] != "1.0": errors.append(f"{prefix}: unsupported schema_version")
        if not isinstance(record["id"], str) or not record["id"].strip() or record["id"] in ids: errors.append(f"{prefix}: duplicate or invalid id")
        ids.add(record.get("id"))
        if record["split"] not in SPLITS: errors.append(f"{prefix}: invalid split")
        if not isinstance(record["question"], str) or not record["question"].strip(): errors.append(f"{prefix}: invalid question")
        key = _norm(record.get("question", ""))
        if key in questions and questions[key] != record.get("split"): errors.append(f"{prefix}: question appears across splits")
        questions[key] = record.get("split")
        gold = record["gold_passage_ids"]
        if not isinstance(record["answerable"], bool) or not isinstance(gold, list): errors.append(f"{prefix}: invalid answerability or gold passages")
        if record.get("answerable") and (not gold or not isinstance(record["reference_answer"], str) or not record["reference_answer"].strip()): errors.append(f"{prefix}: answerable records require gold passages and a reference answer")
        if not record.get("answerable") and gold: errors.append(f"{prefix}: unsupported record cannot have gold passages")
        for span in record.get("evidence_spans", []):
            if not isinstance(span, Mapping) or str(span.get("passage_id")) not in {str(value) for value in gold} or not isinstance(span.get("start_char"), int) or not isinstance(span.get("end_char"), int) or span["start_char"] < 0 or span["end_char"] <= span["start_char"]:
                errors.append(f"{prefix}: invalid evidence span")
        for claim in record.get("claims", []):
            if not isinstance(claim, Mapping) or not isinstance(claim.get("text"), str) or not claim["text"].strip():
                errors.append(f"{prefix}: invalid claim")
                continue
            for review in claim.get("reviews", []):
                if review.get("provenance") != "human" or not review.get("reviewer_id") or review.get("label") not in CLAIM_LABELS:
                    errors.append(f"{prefix}: invalid human claim review")
            adjudication = claim.get("adjudication")
            if adjudication and (adjudication.get("provenance") != "human" or not adjudication.get("adjudicator_id") or adjudication.get("label") not in CLAIM_LABELS):
                errors.append(f"{prefix}: invalid claim adjudication")
    return errors


def adjudicated_claim_labels(record: Mapping[str, Any]) -> dict[str, str]:
    """Only human adjudications are benchmark ground truth; suggestions stay separate."""
    return {_norm(claim["text"]): claim["adjudication"]["label"] for claim in record.get("claims", []) if claim.get("adjudication", {}).get("provenance") == "human"}


def reviewer_agreement(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    agreements = disagreements = comparable = 0
    by_reviewer = Counter()
    for record in records:
        for claim in record.get("claims", []):
            labels = {review["reviewer_id"]: review["label"] for review in claim.get("reviews", []) if review.get("provenance") == "human"}
            reviewers = sorted(labels)
            for left_index, left in enumerate(reviewers):
                for right in reviewers[left_index + 1:]:
                    comparable += 1; by_reviewer[left] += 1; by_reviewer[right] += 1
                    if labels[left] == labels[right]: agreements += 1
                    else: disagreements += 1
    return {"comparable_pairs": comparable, "agreements": agreements, "disagreements": disagreements, "pairwise_agreement": agreements / comparable if comparable else None, "reviewer_pair_contributions": dict(by_reviewer)}


def append_review(path: str | Path, *, record_id: str, claim_id: str, reviewer_id: str, label: str, rationale: str) -> None:
    """Add a human review; never creates labels or silently adjudicates disagreement."""
    if label not in CLAIM_LABELS or not reviewer_id.strip() or not rationale.strip(): raise ValueError("reviewer, rationale, and a valid label are required")
    records = load_review_dataset(path)
    matches = [record for record in records if record.get("id") == record_id]
    if len(matches) != 1: raise ValueError("record_id must identify exactly one record")
    claims = [claim for claim in matches[0].get("claims", []) if claim.get("id") == claim_id]
    if len(claims) != 1: raise ValueError("claim_id must identify exactly one claim")
    claims[0].setdefault("reviews", []).append({"reviewer_id": reviewer_id, "label": label, "rationale": rationale, "provenance": "human"})
    errors = validate_review_dataset(records)
    if errors: raise ValueError("dataset invalid: " + "; ".join(errors))
    Path(path).write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def adjudicate_claim(path: str | Path, *, record_id: str, claim_id: str, adjudicator_id: str, label: str, rationale: str) -> None:
    """Record an explicit human resolution without overwriting individual reviews."""
    if label not in CLAIM_LABELS or not adjudicator_id.strip() or not rationale.strip(): raise ValueError("adjudicator, rationale, and a valid label are required")
    records = load_review_dataset(path)
    record = next((item for item in records if item.get("id") == record_id), None)
    if record is None: raise ValueError("record_id must identify exactly one record")
    claim = next((item for item in record.get("claims", []) if item.get("id") == claim_id), None)
    if claim is None: raise ValueError("claim_id must identify exactly one claim")
    if not claim.get("reviews"): raise ValueError("at least one human review is required before adjudication")
    claim["adjudication"] = {"adjudicator_id": adjudicator_id, "label": label, "rationale": rationale, "provenance": "human"}
    errors = validate_review_dataset(records)
    if errors: raise ValueError("dataset invalid: " + "; ".join(errors))
    Path(path).write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in records), encoding="utf-8")


def export_csv_report(report: Mapping[str, Any], path: str | Path) -> None:
    rows = []
    for mode, mode_report in report.get("reports", {}).items():
        for prediction in mode_report.get("predictions", []):
            rows.append({"mode": mode, "id": prediction.get("id"), "question": prediction.get("question"), "answerable": prediction.get("answerable"), "accepted": prediction.get("accepted"), "retrieved_ids": ";".join(str(item.get("id")) for item in prediction.get("retrieved", [])), "retrieval_latency_ms": prediction.get("retrieval_latency_ms")})
    fields = ["mode", "id", "question", "answerable", "accepted", "retrieved_ids", "retrieval_latency_ms"]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
