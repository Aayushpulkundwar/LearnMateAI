"""Strict evaluator for the frozen nine-chapter retrieval comparison."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXPECTED_CORPUS = "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8"
MODES = {"dense": "Dense", "fts": "PostgreSQL FTS", "hybrid": "Hybrid"}


def precision_at_5(ranked: list[str], relevant: set[str]) -> float:
    return sum(item in relevant for item in ranked[:5]) / 5.0


def recall_at_5(ranked: list[str], relevant: set[str]) -> float:
    return sum(item in relevant for item in ranked[:5]) / len(relevant) if relevant else 0.0


def mrr_at_10(ranked: list[str], relevant: set[str]) -> float:
    return next((1.0 / rank for rank, item in enumerate(ranked[:10], 1) if item in relevant), 0.0)


def ndcg_at_10(ranked: list[str], relevant: set[str]) -> float:
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item in enumerate(ranked[:10], 1) if item in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), 10) + 1))
    return dcg / ideal if ideal else 0.0


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(path: Path) -> list[dict[str, Any]]:
    raw = _read_json(path)
    if isinstance(raw, dict):
        if raw.get("corpus_sha256") != EXPECTED_CORPUS:
            raise ValueError(f"Corpus fingerprint mismatch in {path.name}")
        raw = raw.get("queries", raw.get("results"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON list of query records in {path}")
    return raw


def validate_run_files(root: Path = ROOT) -> dict[str, Any]:
    """Validate raw live retrieval traces independently of human qrels."""
    manifest = _read_json(root / "experiment_manifest.json")
    report = _read_json(root / "frozen_corpus_report.json")
    dataset_path = root / "datasets" / "questions.jsonl"
    dataset = [json.loads(x) for x in dataset_path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    ids = {q.get("id") for q in dataset}
    if manifest.get("frozen_run_id") != "nine_science_03" or manifest.get("corpus_sha256") != EXPECTED_CORPUS or report.get("corpus_sha256") != EXPECTED_CORPUS:
        raise ValueError("Frozen run metadata mismatch")
    if len(dataset) != 40 or len(ids) != 40 or any(q.get("corpus_sha256") != EXPECTED_CORPUS for q in dataset):
        raise ValueError("Research question dataset identity/count mismatch")
    corpus_docs = {str(d["id"]): int(d["chapter_number"]) for d in report.get("documents", [])}
    if set(corpus_docs.values()) != {1, 2, 3, 7, 9, 10, 11, 12, 13}:
        raise ValueError("Frozen allowlist must contain only the nine approved chapters")
    snapshot_path = root.parent.parent / "results" / "nine_science_03" / "corpus.json"
    if not snapshot_path.is_file():
        raise FileNotFoundError("Frozen passage snapshot is required to validate ranking provenance")
    snapshot = _read_json(snapshot_path)
    if snapshot.get("corpus_sha256") != EXPECTED_CORPUS or len(snapshot.get("chunks", [])) != 643:
        raise ValueError("Frozen snapshot identity or passage count mismatch")
    chunks = {str(c["id"]): c for c in snapshot["chunks"]}
    expected_dataset_sha = sha256(dataset_path)
    validated: dict[str, list[dict[str, Any]]] = {}
    summary = {"frozen_run_id": "nine_science_03", "corpus_sha256": EXPECTED_CORPUS, "dataset_sha256": expected_dataset_sha, "questions": len(ids), "modes": {}}
    for mode in MODES:
        path = root / "runs" / f"{mode}.json"
        payload = _read_json(path)
        if payload.get("run_id") != "nine_science_03" or payload.get("corpus_sha256") != EXPECTED_CORPUS or payload.get("dataset_sha256") != expected_dataset_sha or payload.get("mode") != mode or payload.get("top_k") != 10:
            raise ValueError(f"Run identity/config mismatch in {path.name}")
        rows = _records(path)
        by_id = {r.get("question_id"): r for r in rows}
        if len(by_id) != 40 or set(by_id) != ids:
            raise ValueError(f"Expected exactly the frozen 40 question IDs in {path.name}")
        successes = failures = 0
        for qid, row in by_id.items():
            if row.get("mode") != mode or row.get("status") not in ("success", "failed"):
                raise ValueError(f"Invalid query condition/status in {path.name}: {qid}")
            successes += row["status"] == "success"; failures += row["status"] == "failed"
            latency = row.get("latency_ms")
            if not isinstance(latency, (int, float)) or latency < 0:
                raise ValueError(f"Invalid latency in {path.name}: {qid}")
            ranked = row.get("pre_gate_ranked")
            if not isinstance(ranked, list) or len(ranked) > 10:
                raise ValueError(f"Invalid top-10 pre-gate ranking in {path.name}: {qid}")
            seen = set()
            for position, item in enumerate(ranked, 1):
                cid = str(item.get("chunk_id", ""))
                frozen = chunks.get(cid)
                if not cid or cid in seen or not frozen:
                    raise ValueError(f"Duplicate or out-of-snapshot chunk in {path.name}: {qid}")
                seen.add(cid)
                if str(item.get("document_id")) != str(frozen["document_id"]) or frozen["document_id"] not in corpus_docs or corpus_docs[frozen["document_id"]] not in {1,2,3,7,9,10,11,12,13}:
                    raise ValueError(f"Excluded or mismatched source provenance in {path.name}: {qid}")
                if item.get("rank") != position:
                    raise ValueError(f"Ranking order/rank mismatch in {path.name}: {qid}")
        validated[mode] = rows
        summary["modes"][mode] = {"queries": len(rows), "successful": successes, "failed": failures}
    return summary


def evaluate(root: Path = ROOT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _read_json(root / "experiment_manifest.json")
    if manifest.get("frozen_run_id") != "nine_science_03" or manifest.get("corpus_sha256") != EXPECTED_CORPUS:
        raise ValueError("Manifest does not identify the expected frozen corpus")
    corpus_report = _read_json(root / "frozen_corpus_report.json")
    if corpus_report.get("corpus_sha256") != EXPECTED_CORPUS:
        raise ValueError("Frozen corpus report fingerprint mismatch")
    snapshot_path = root.parent.parent / "results" / "nine_science_03" / "corpus.json"
    allowed_chunks: dict[str, dict[str, Any]] = {}
    if snapshot_path.is_file():
        frozen = _read_json(snapshot_path)
        if frozen.get("corpus_sha256") != EXPECTED_CORPUS:
            raise ValueError("Frozen passage snapshot fingerprint mismatch")
        allowed_chunks = {str(c["id"]): c for c in frozen.get("chunks", [])}
        if len(allowed_chunks) != 643:
            raise ValueError("Frozen passage snapshot must contain the recorded 643 chunks")
    gold_path = root / "gold.json"
    if not gold_path.is_file():
        raise FileNotFoundError("Validated human-adjudicated gold.json is required; no metrics were produced")
    metadata_path = root / "gold_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("gold_metadata.json from the validated two-reviewer adjudication workflow is required")
    gold_metadata = _read_json(metadata_path)
    if gold_metadata.get("corpus_sha256") != EXPECTED_CORPUS or gold_metadata.get("questions") != 40 or gold_metadata.get("unjudged_passages_are_not_negative") is not True:
        raise ValueError("Gold metadata is incomplete or not compatible with the frozen 40-question review protocol")
    gold_raw = _read_json(gold_path)
    if isinstance(gold_raw, dict):
        if gold_raw.get("corpus_sha256") != EXPECTED_CORPUS:
            raise ValueError("Gold corpus fingerprint mismatch")
        gold = gold_raw.get("questions", gold_raw.get("records"))
    else:
        gold = gold_raw
    if not isinstance(gold, list):
        raise ValueError("Gold judgments must be a validated JSON list")
    dataset_path = root / "datasets" / "questions.jsonl"
    dataset = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(dataset) != 40 or len({q.get("id") for q in dataset}) != 40:
        raise ValueError("The preserved 40-question research dataset is missing or changed")
    source_by_id = {q["id"]: q for q in dataset}
    # Require the raw traces to pass the same frozen corpus and provenance checks
    # when the evaluator is called as a library as well as from its CLI.
    validate_run_files(root)

    gold_by_id: dict[str, dict[str, Any]] = {}
    for row in gold:
        qid = row.get("id", row.get("question_id"))
        if not qid or qid in gold_by_id:
            raise ValueError("Missing or duplicate question ID in gold")
        if row.get("corpus_sha256", EXPECTED_CORPUS) != EXPECTED_CORPUS:
            raise ValueError(f"Gold fingerprint mismatch for {qid}")
        source = source_by_id.get(qid)
        if not source or any(row.get(field) != source.get(field) for field in ("question", "split", "chapter_number", "document_id")):
            raise ValueError(f"Gold question metadata differs from preserved dataset: {qid}")
        if not str(row.get("gold_provenance", "")).startswith("two independent human judgments"):
            raise ValueError(f"Gold provenance is not adjudicated human review: {qid}")
        if row.get("relevance_review", {}).get("status") == "pending":
            raise ValueError(f"Unreviewed judgment in gold: {qid}")
        gold_by_id[qid] = row

    runs: dict[str, dict[str, dict[str, Any]]] = {}
    for mode in MODES:
        path = root / "runs" / f"{mode}.json"
        rows = _records(path)
        payload = _read_json(path)
        if isinstance(payload, dict) and payload.get("mode") not in (None, mode):
            raise ValueError(f"Run mode mismatch in {path.name}")
        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            qid = row.get("question_id", row.get("id"))
            if not qid or qid in by_id:
                raise ValueError(f"Missing or duplicate query ID in {path.name}")
            by_id[qid] = row
        runs[mode] = by_id
    query_sets = [set(x) for x in runs.values()]
    if not query_sets or any(ids != query_sets[0] for ids in query_sets[1:]):
        raise ValueError("Retrieval modes must contain the identical query set")
    if query_sets[0] != set(source_by_id):
        raise ValueError("Every retrieval mode must contain exactly the preserved 40-question dataset")
    if query_sets[0] - gold_by_id.keys():
        raise ValueError("Retrieval run contains questions without reviewed gold records")

    summary: dict[str, Any] = {
        "frozen_run_id": "nine_science_03", "corpus_sha256": EXPECTED_CORPUS,
        "gold_sha256": sha256(gold_path), "incomplete_pooling_policy": "answerable queries with any unjudged top-10 result are excluded from ranking metrics, reported separately; unjudged is never negative",
        "modes": {}, "unanswerable_question_ids": [], "excluded_incomplete_question_ids": {},
    }
    details: list[dict[str, Any]] = []
    for qid in sorted(query_sets[0]):
        g = gold_by_id[qid]
        answerable = g.get("answerable")
        if not isinstance(answerable, bool):
            raise ValueError(f"Gold answerability must be explicit boolean: {qid}")
        judgments = g.get("relevance_judgments", g.get("judgments", {}))
        if not isinstance(judgments, dict):
            raise ValueError(f"Gold relevance judgments must be a chunk-ID mapping: {qid}")
        positives = {chunk for chunk, val in judgments.items() if val == 1}
        if answerable and not positives:
            raise ValueError(f"Answerable question lacks adjudicated relevant support: {qid}")
        if not answerable:
            summary["unanswerable_question_ids"].append(qid)
        for mode, by_id in runs.items():
            rec = by_id[qid]
            ranked_records = rec.get("pre_gate_ranked", rec.get("ranked", rec.get("ranked_chunks", []))) or []
            if isinstance(ranked_records, list):
                ids = [x if isinstance(x, str) else x.get("chunk_id", x.get("id")) for x in ranked_records]
                if allowed_chunks:
                    for item, chunk_id in zip(ranked_records, ids):
                        frozen_chunk = allowed_chunks.get(str(chunk_id))
                        if frozen_chunk is None:
                            raise ValueError(f"Out-of-snapshot chunk returned for {qid}/{mode}")
                        if isinstance(item, dict) and item.get("document_id") and str(item["document_id"]) != frozen_chunk["document_id"]:
                            raise ValueError(f"Chunk/document provenance mismatch for {qid}/{mode}")
                        if frozen_chunk["document_id"] not in {d["id"] for d in corpus_report.get("documents", [])}:
                            raise ValueError(f"Excluded-document chunk returned for {qid}/{mode}")
            else:
                raise ValueError(f"Invalid ranking schema for {qid}/{mode}")
            if any(not x for x in ids) or len(ids) > 10 or len(ids) != len(set(ids)):
                raise ValueError(f"Ranking IDs invalid, duplicate, or >10 for {qid}/{mode}")
            latency = rec.get("latency_ms")
            if latency is None or not isinstance(latency, (int, float)) or latency < 0:
                raise ValueError(f"Missing/invalid monotonic retrieval latency for {qid}/{mode}")
            valid = answerable
            incomplete = answerable and any(chunk not in judgments for chunk in ids[:10])
            scores = {"precision_at_5": None, "recall_at_5": None, "mrr_at_10": None, "ndcg_at_10": None}
            if valid and not incomplete:
                scores = {"precision_at_5": precision_at_5(ids, positives),
                          "recall_at_5": recall_at_5(ids, positives),
                          "mrr_at_10": mrr_at_10(ids, positives),
                          "ndcg_at_10": ndcg_at_10(ids, positives)}
            elif incomplete:
                summary["excluded_incomplete_question_ids"].setdefault(mode, []).append(qid)
            details.append({"question_id": qid, "split": g.get("split"), "mode": mode, "answerable": answerable,
                            "incomplete_pooling": incomplete, **scores, "latency_ms": float(latency), "status": rec.get("status", "unknown")})
    for mode in MODES:
        rows = [r for r in details if r["mode"] == mode]
        scored = [r for r in rows if r["answerable"] and not r["incomplete_pooling"]]
        latencies = [r["latency_ms"] for r in rows]
        metric_names = ("precision_at_5", "recall_at_5", "mrr_at_10", "ndcg_at_10")
        summary["modes"][mode] = {
            "questions_total": len(rows), "answerable_scored": len(scored),
            "unanswerable_n": sum(not r["answerable"] for r in rows),
            "incomplete_pooling_n": sum(r["incomplete_pooling"] for r in rows),
            "execution_status_counts": {status: sum(r["status"] == status for r in rows) for status in sorted({r["status"] for r in rows})},
            "metrics": {name: {"mean": statistics.fmean(r[name] for r in scored) if scored else None, "n": len(scored)} for name in metric_names},
            "latency_ms": {"mean": statistics.fmean(latencies) if latencies else None, "median": statistics.median(latencies) if latencies else None,
                           "p95": percentile(latencies, .95), "n": len(latencies)},
        }
    return summary, details


def export(summary: dict[str, Any], details: list[dict[str, Any]], root: Path = ROOT) -> None:
    out = root / "results"
    out.mkdir(parents=True, exist_ok=True)
    targets = [out / "retrieval_metrics.json", out / "retrieval_metrics.csv", out / "per_question_metrics.csv", out / "retrieval_comparison_table.md"]
    if any(p.exists() for p in targets):
        raise FileExistsError("Refusing to overwrite existing retrieval result artifacts")
    (out / targets[0].name).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with targets[1].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["mode", "metric", "mean", "n"])
        for mode, data in summary["modes"].items():
            for metric, val in data["metrics"].items(): w.writerow([mode, metric, val["mean"], val["n"]])
            for metric, val in data["latency_ms"].items(): w.writerow([mode, f"latency_{metric}_ms", val, data["latency_ms"]["n"]])
    with targets[2].open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(details[0]) if details else []); w.writeheader(); w.writerows(details)
    rows = ["| Retrieval method | P@5 | R@5 | MRR@10 | nDCG@10 | Median latency | P95 latency |", "|---|---:|---:|---:|---:|---:|---:|"]
    for mode, label in MODES.items():
        d = summary["modes"][mode]; m = d["metrics"]; l = d["latency_ms"]
        fmt = lambda x: "N/A" if x is None else f"{x:.4f}"
        rows.append(f"| {label} | {fmt(m['precision_at_5']['mean'])} | {fmt(m['recall_at_5']['mean'])} | {fmt(m['mrr_at_10']['mean'])} | {fmt(m['ndcg_at_10']['mean'])} | {fmt(l['median'])} ms | {fmt(l['p95'])} ms |")
    targets[3].write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--validate-only", action="store_true", help="Validate real retrieval traces without relevance labels")
    args = parser.parse_args()
    validation = validate_run_files(args.root)
    if args.validate_only:
        print(json.dumps(validation, indent=2))
        return 0
    summary, details = evaluate(args.root)
    export(summary, details, args.root)
    print(f"Evaluated {len(details)} query-mode records; exports written to {args.root / 'results'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
