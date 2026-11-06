"""Blinded two-reviewer answer scoring, disagreement validation and export."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCORES = ("correctness", "faithfulness", "explanation_quality", "citation_support")
REQUIRED = ("question_id", "question", "reference_answer", "evidence_passages", "answer_a", "answer_b",
            "score_a_correctness", "score_a_faithfulness", "score_a_explanation_quality", "score_a_citation_support",
            "score_b_correctness", "score_b_faithfulness", "score_b_explanation_quality", "score_b_citation_support",
            "reviewer_id", "rationale", "unsupported_claims", "review_duration_seconds")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def create_worksheets(root: Path = ROOT, seed: int = 20261030) -> list[Path]:
    base = _load(root / "generation" / "no_retrieval.json")
    rag = _load(root / "generation" / "rag.json")
    if base.get("corpus_sha256") != rag.get("corpus_sha256") or base.get("corpus_sha256") != "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8":
        raise ValueError("Generation outputs must match the frozen corpus")
    bmap = {r["question_id"]: r for r in base.get("records", []) if r.get("status") == "success"}
    rmap = {r["question_id"]: r for r in rag.get("records", []) if r.get("status") == "success"}
    expected_ids = set(base.get("selected_question_ids", []))
    if set(bmap) != set(rmap) or set(bmap) != expected_ids or set(rag.get("selected_question_ids", [])) != expected_ids or not bmap:
        raise ValueError("Both conditions must have successful answers for identical questions")
    gold_path = root / "gold.json"
    gold = _load(gold_path) if gold_path.exists() else []
    if gold_path.exists():
        metadata = _load(root / "gold_metadata.json")
        if metadata.get("corpus_sha256") != base["corpus_sha256"] or metadata.get("questions") != 40 or metadata.get("unjudged_passages_are_not_negative") is not True:
            raise ValueError("Gold metadata is not compatible with the two-reviewer frozen-corpus protocol")
    if isinstance(gold, dict):
        gold = gold.get("questions", gold.get("records", []))
    goldmap = {x.get("id", x.get("question_id")): x for x in gold}
    corpus_path = root.parent.parent / "results" / "nine_science_03" / "corpus.json"
    if not corpus_path.is_file():
        raise FileNotFoundError("Frozen corpus passages are unavailable")
    corpus = _load(corpus_path)
    if corpus.get("corpus_sha256") != base.get("corpus_sha256") or len(corpus.get("chunks", [])) != 643:
        raise ValueError("Frozen passage snapshot identity/count mismatch")
    chunks = {str(c.get("id", c.get("chunk_id"))): c for c in corpus.get("chunks", [])}
    allowed_documents = {str(d["id"]) for d in _load(root / "frozen_corpus_report.json").get("documents", [])}
    if gold_path.exists() and len(gold) != 40:
        raise ValueError("Gold must cover the preserved 40-question dataset")
    output_dir = root / "annotations"
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = output_dir / "answer_blinding_key.json"
    sheet_paths = [output_dir / f"answer_reviewer_{i}.csv" for i in (1, 2)]
    if mapping_path.exists() or any(p.exists() for p in sheet_paths):
        raise FileExistsError("Refusing to overwrite answer review artifacts")
    rng = random.Random(seed)
    mapping: dict[str, Any] = {"seed": seed, "question_order_and_condition_mapping": {}}
    rows_by_reviewer: list[list[dict[str, Any]]] = [[], []]
    for qid in sorted(bmap):
        candidates = [("no_retrieval", bmap[qid]), ("rag", rmap[qid])]
        rng.shuffle(candidates)
        qgold = goldmap.get(qid, {})
        if qgold:
            if qgold.get("corpus_sha256") != base["corpus_sha256"] or not str(qgold.get("gold_provenance", "")).startswith("two independent human judgments"):
                raise ValueError(f"Gold review provenance/fingerprint mismatch for {qid}")
        evidence = []
        judgments = qgold.get("relevance_judgments", {})
        positives = {chunk_id for chunk_id, label in judgments.items() if label == 1}
        for chunk_id in sorted(positives):
            chunk = chunks.get(str(chunk_id))
            if not chunk:
                raise ValueError(f"Gold evidence chunk is absent from frozen corpus: {chunk_id}")
            if str(chunk.get("document_id")) not in allowed_documents:
                raise ValueError(f"Gold evidence document link is invalid: {chunk_id}")
            evidence.append({"chunk_id": chunk_id, "document_id": chunk.get("document_id"),
                             "chapter": chunk.get("chapter_number", chunk.get("chapter")),
                             "page": chunk.get("page_number", chunk.get("page")),
                             "passage": chunk.get("content", chunk.get("text", ""))})
        for span in qgold.get("evidence_spans", []):
            chunk = chunks.get(str(span.get("passage_id"))) if isinstance(span, dict) else None
            if not chunk or not isinstance(span.get("start_char"), int) or not isinstance(span.get("end_char"), int) or not 0 <= span["start_char"] < span["end_char"] <= len(chunk.get("content", "")):
                raise ValueError(f"Invalid gold evidence span link for {qid}")
        pair = {"A": candidates[0][0], "B": candidates[1][0]}
        mapping["question_order_and_condition_mapping"][qid] = {**pair}
        a, b = candidates[0][1], candidates[1][1]
        row = {"question_id": qid, "question": bmap[qid].get("question", ""),
               "reference_answer": qgold.get("reference_answer") or "",
               "evidence_passages": json.dumps(evidence, ensure_ascii=False),
               "answer_a": a.get("answer", ""), "answer_b": b.get("answer", ""),
               **{field: "" for field in REQUIRED if field.startswith("score_")},
               "reviewer_id": "", "rationale": "", "unsupported_claims": "", "review_duration_seconds": ""}
        immutable = {key: row[key] for key in ("question", "reference_answer", "evidence_passages", "answer_a", "answer_b")}
        mapping["question_order_and_condition_mapping"][qid]["content_sha256"] = hashlib.sha256(
            json.dumps(immutable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        for rows in rows_by_reviewer:
            rows.append(dict(row))
    for path, rows in zip(sheet_paths, rows_by_reviewer):
        with path.open("x", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=REQUIRED); writer.writeheader(); writer.writerows(rows)
    with mapping_path.open("x", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2); f.write("\n")
    return sheet_paths


def _read_review(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if any(tuple(row.keys()) != REQUIRED for row in rows):
        raise ValueError(f"Review schema mismatch in {path.name}")
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        qid = row["question_id"]
        if not qid or qid in by_id or not row["reviewer_id"].strip() or not row["rationale"].strip():
            raise ValueError("Duplicate question or missing reviewer/rationale")
        for label in ("a", "b"):
            for score in SCORES:
                key = f"score_{label}_{score}"
                try: value = int(row[key])
                except (TypeError, ValueError): raise ValueError(f"Missing/invalid score {key} for {qid}")
                if value not in (0, 1, 2): raise ValueError(f"Out-of-range score {key} for {qid}")
        duration = row["review_duration_seconds"].strip()
        if duration and (not math.isfinite(float(duration)) or float(duration) < 0): raise ValueError("Invalid review duration")
        by_id[qid] = row
    if not by_id: raise ValueError("Empty answer review")
    return by_id


def import_reviews(root: Path = ROOT, reviewer1: Path | None = None, reviewer2: Path | None = None) -> Path:
    reviewer1 = reviewer1 or root / "annotations" / "answer_reviewer_1.csv"
    reviewer2 = reviewer2 or root / "annotations" / "answer_reviewer_2.csv"
    left, right = _read_review(reviewer1), _read_review(reviewer2)
    if set(left) != set(right): raise ValueError("Reviewers must score identical question IDs")
    ids1 = {row["reviewer_id"].strip() for row in left.values()}
    ids2 = {row["reviewer_id"].strip() for row in right.values()}
    if len(ids1) != 1 or len(ids2) != 1 or ids1 == ids2: raise ValueError("Require two distinct reviewer identities")
    base = _load(root / "generation" / "no_retrieval.json")
    rag = _load(root / "generation" / "rag.json")
    expected = set(base.get("selected_question_ids", []))
    if set(left) != expected: raise ValueError("Reviewed question IDs differ from immutable generation IDs")
    bmap = {r["question_id"]: r for r in base["records"]}
    rmap = {r["question_id"]: r for r in rag["records"]}
    mapping = _load(root / "annotations" / "answer_blinding_key.json")["question_order_and_condition_mapping"]
    disputes = []
    for qid in sorted(left):
        for immutable in ("question", "reference_answer", "evidence_passages", "answer_a", "answer_b"):
            if left[qid][immutable] != right[qid][immutable]:
                raise ValueError(f"Question/evidence/answer content changed between review files: {qid}")
        immutable = {key: left[qid][key] for key in ("question", "reference_answer", "evidence_passages", "answer_a", "answer_b")}
        digest = hashlib.sha256(json.dumps(immutable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        if digest != mapping.get(qid, {}).get("content_sha256"):
            raise ValueError(f"Immutable question/evidence/answer content was modified: {qid}")
        if {key: mapping.get(qid, {}).get(key) for key in ("A", "B")} not in ({"A": "rag", "B": "no_retrieval"}, {"A": "no_retrieval", "B": "rag"}):
            raise ValueError("Blinding map is invalid")
        for reviewer in (left[qid], right[qid]):
            pair = mapping[qid]
            for label in ("a", "b"):
                output = bmap[qid] if pair[label.upper()] == "no_retrieval" else rmap[qid]
                if reviewer[f"answer_{label}"] != output.get("answer", ""):
                    raise ValueError(f"Answer text changed for {qid}/{label}")
        for label in ("a", "b"):
            for score in SCORES:
                key = f"score_{label}_{score}"
                if left[qid][key] != right[qid][key]: disputes.append({"question_id": qid, "answer": label.upper(), "metric": score,
                    "reviewer_1": left[qid][key], "reviewer_2": right[qid][key], "final_score": "", "adjudicator_id": "", "rationale": "", "date": ""})
    out = root / "annotations" / "answer_disagreements.csv"
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    fields = ["question_id", "answer", "metric", "reviewer_1", "reviewer_2", "final_score", "adjudicator_id", "rationale", "date"]
    with out.open("x", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(disputes)
    return out


def adjudicate_and_export(root: Path = ROOT) -> Path:
    # Import validates both files and writes the disagreement worksheet. Human resolution is required.
    dispute_path = root / "annotations" / "answer_disagreements.csv"
    if not dispute_path.exists():
        raise FileNotFoundError("Import both reviewers first to generate answer_disagreements.csv")
    with dispute_path.open(encoding="utf-8-sig", newline="") as f: disputes = list(csv.DictReader(f))
    for d in disputes:
        if not d["final_score"].strip() or not d["adjudicator_id"].strip() or not d["rationale"].strip() or not d["date"].strip():
            raise ValueError("Every disagreement requires explicit human adjudication before export")
        if d["final_score"] not in ("0", "1", "2"): raise ValueError("Invalid adjudicated score")
    left, right = _read_review(root / "annotations" / "answer_reviewer_1.csv"), _read_review(root / "annotations" / "answer_reviewer_2.csv")
    by_dispute = {(d["question_id"], d["answer"], d["metric"]): d for d in disputes}
    mapping = _load(root / "annotations" / "answer_blinding_key.json")["question_order_and_condition_mapping"]
    sums: dict[str, dict[str, list[int]]] = {"rag": {m: [] for m in SCORES}, "no_retrieval": {m: [] for m in SCORES}}
    for qid in left:
        for label in ("a", "b"):
            condition = mapping[qid][label.upper()]
            for metric in SCORES:
                key = f"score_{label}_{metric}"
                scores = [int(left[qid][key]), int(right[qid][key])]
                d = by_dispute.get((qid, label.upper(), metric))
                value = int(d["final_score"]) if d else scores[0]
                sums[condition][metric].append(value)
    result = {condition: {metric: {"mean": sum(vals)/len(vals), "n": len(vals)} for metric, vals in metrics.items()} for condition, metrics in sums.items()}
    comparisons = [(left[qid][f"score_{label}_{metric}"], right[qid][f"score_{label}_{metric}"])
                   for qid in left for label in ("a", "b") for metric in SCORES]
    agreement_n = sum(a == b for a, b in comparisons)
    result["review"] = {"question_count": len(left), "reviewer_ids": sorted(ids1 | ids2),
                         "score_comparisons": len(comparisons), "raw_agreement": agreement_n / len(comparisons) if comparisons else None,
                         "agreements": agreement_n, "disagreements": len(disputes), "adjudicated": len(disputes)}
    out = root / "results" / "generation_comparison.json"
    table = root / "results" / "generation_comparison_table.md"
    if out.exists() or table.exists(): raise FileExistsError("Refusing to overwrite existing answer-comparison artifacts")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f: json.dump(result, f, indent=2); f.write("\n")
    lines = ["| Condition | Correctness | Faithfulness | Explanation quality | Citation support* | Questions |", "|---|---:|---:|---:|---:|---:|"]
    for condition, label in (("no_retrieval", "Retrieval-free Llama 3 8B"), ("rag", "LearnMateAI RAG")):
        lines.append("| " + label + " | " + " | ".join(f"{result[condition][m]['mean']:.3f}" for m in SCORES) + f" | {len(left)} |")
    lines.extend(["", "*Citation-support scores are interpreted separately: the retrieval-free condition is not supplied with textbook sources and cannot demonstrate source attribution."])
    with table.open("x", encoding="utf-8") as f: f.write("\n".join(lines) + "\n")
    return out


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("worksheets"); s.add_argument("--seed", type=int, default=20261030)
    s = sub.add_parser("import")
    s = sub.add_parser("export")
    args = p.parse_args()
    if args.command == "worksheets": print("\n".join(map(str, create_worksheets(seed=args.seed))))
    elif args.command == "import": print(import_reviews())
    else: print(adjudicate_and_export())
    return 0


if __name__ == "__main__": raise SystemExit(main())
