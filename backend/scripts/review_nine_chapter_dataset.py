"""Export a frozen-corpus CSV for human qrel review and import approved reviews."""
import argparse
import csv
import json
import os
from pathlib import Path

from app.evaluation.nine_chapter_corpus import fingerprint, validate_judgments


FIELDS = ["id", "split", "chapter_number", "chapter_title", "document_id", "corpus_sha256",
          "question", "expected_answer", "proposed_relevant_chunk_ids", "proposed_passages",
          "decision", "reviewer_id", "rationale", "answerable", "gold_passage_ids",
          "reference_answer", "evidence_spans_json"]


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_frozen(run_dir):
    run_dir = Path(run_dir)
    corpus = json.loads((run_dir / "corpus.json").read_text(encoding="utf-8"))
    expected = corpus.pop("corpus_sha256")
    if fingerprint(corpus) != expected:
        raise ValueError("Frozen corpus fingerprint does not match corpus.json.")
    candidates = read_jsonl(run_dir / "questions.candidates.jsonl")
    if len(candidates) != 50 or any(r.get("corpus_sha256") != expected for r in candidates):
        raise ValueError("Candidate questions do not match this 50-question frozen corpus run.")
    approved_ids = set(corpus["approved"].values())
    chunk_ids = {c["id"] for c in corpus["chunks"]}
    if any(r.get("document_id") not in approved_ids for r in candidates):
        raise ValueError("Candidate set contains a document outside the approved chapters.")
    for record in candidates:
        for suggestion in record.get("candidate_passages", []):
            if suggestion.get("passage_id") not in chunk_ids or suggestion.get("document_id") not in approved_ids:
                raise ValueError("Candidate passage falls outside the frozen corpus.")
    titles = {d["id"]: d["title"] for d in corpus["documents"]}
    # Stored chunk.chapter is the chapter label; document.title may be a generic upload title.
    chunk_titles = {c["document_id"]: c["chapter"] for c in corpus["chunks"]}
    return corpus, expected, candidates, titles, chunk_titles


def export_csv(run_dir, output):
    corpus, sha, candidates, _titles, chunk_titles = load_frozen(run_dir)
    chunks = {c["id"]: c for c in corpus["chunks"]}
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite review file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for record in candidates:
            suggestions = record.get("candidate_passages", [])
            displays = []
            for item in suggestions:
                chunk = chunks[item["passage_id"]]
                displays.append("CHUNK: {id}\nPAGE: {page}\nPASSAGE:\n{text}".format(
                    id=chunk["id"], page=chunk["page_number"], text=chunk["content"]))
            writer.writerow({"id": record["id"], "split": record["split"],
                "chapter_number": record["chapter_number"], "chapter_title": chunk_titles[record["document_id"]],
                "document_id": record["document_id"], "corpus_sha256": sha, "question": record["question"],
                "expected_answer": record.get("reference_answer") or "(not supplied; reviewer must author if answerable)",
                "proposed_relevant_chunk_ids": ";".join(i["passage_id"] for i in suggestions),
                "proposed_passages": "\n\n".join(displays), "decision": "", "reviewer_id": "", "rationale": "",
                "answerable": "", "gold_passage_ids": "", "reference_answer": "", "evidence_spans_json": ""})
    print(f"Wrote {len(candidates)} pending review rows from frozen corpus {sha}: {output}")


def parse_bool(value, field, record_id):
    normalized = (value or "").strip().casefold()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{record_id}: {field} must be explicitly true or false.")
    return normalized == "true"


def import_csv(run_dir, review_csv, output):
    _corpus, sha, candidates, _titles, _chunk_titles = load_frozen(run_dir)
    if Path(output).exists():
        raise FileExistsError(f"Refusing to overwrite existing dataset: {output}")
    with Path(review_csv).open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    original = {r["id"]: r for r in candidates}
    if len(rows) != 50 or len({r.get("id") for r in rows}) != 50 or {r.get("id") for r in rows} != set(original):
        raise ValueError("Review CSV must contain each of the original 50 question IDs exactly once.")
    results = []
    for row in rows:
        base = original[row["id"]]
        if any(row.get(key) != str(base.get(key)) for key in ("split", "document_id", "chapter_number")) or row.get("corpus_sha256") != sha:
            raise ValueError(f"{row.get('id')}: immutable chapter, split, document, or corpus fingerprint changed.")
        decision = (row.get("decision") or "").strip().casefold()
        if decision not in {"approve", "correct"}:
            raise ValueError(f"{row.get('id')}: decision must be approve or correct; rejected/pending rows cannot be exported.")
        if not (row.get("reviewer_id") or "").strip() or not (row.get("rationale") or "").strip():
            raise ValueError(f"{row['id']}: reviewer_id and rationale are required.")
        record = dict(base)
        record["question"] = (row.get("question") or "").strip()
        record["answerable"] = parse_bool(row.get("answerable"), "answerable", row["id"])
        gold = [value.strip() for value in (row.get("gold_passage_ids") or "").replace(",", ";").split(";") if value.strip()]
        record["gold_passage_ids"] = gold
        record["reference_answer"] = (row.get("reference_answer") or "").strip() or None
        raw_spans = (row.get("evidence_spans_json") or "").strip()
        try:
            record["evidence_spans"] = json.loads(raw_spans) if raw_spans else []
        except json.JSONDecodeError as exc:
            raise ValueError(f"{row['id']}: evidence_spans_json is not valid JSON.") from exc
        record["relevance_review"] = {"status": "approved", "provenance": "human",
             "reviewer_id": row["reviewer_id"].strip(), "rationale": row["rationale"].strip(),
             "decision": decision}
        results.append(record)

    # Validate against the immutable snapshot before creating any output.
    frozen = json.loads((Path(run_dir) / "corpus.json").read_text(encoding="utf-8"))
    frozen.pop("corpus_sha256")
    validate_judgments(results, frozen)
    if any(r.get("corpus_sha256") != sha for r in results):
        raise ValueError("Question corpus fingerprints changed during review import.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"Refusing to overwrite temporary dataset: {temporary}")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            for record in results:
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        os.replace(str(temporary), str(output))
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Exported {len(results)} human-reviewed questions (18 dev / 32 test), corpus {sha}: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export-csv")
    export.add_argument("--run-dir", required=True)
    export.add_argument("--output", required=True)
    importer = commands.add_parser("import-csv")
    importer.add_argument("--run-dir", required=True)
    importer.add_argument("--review-csv", required=True)
    importer.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "export-csv":
        export_csv(args.run_dir, args.output)
    else:
        import_csv(args.run_dir, args.review_csv, args.output)


if __name__ == "__main__":
    main()
