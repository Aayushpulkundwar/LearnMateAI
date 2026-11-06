"""Reproducible dense/FTS/hybrid retrieval and blinded two-reviewer workflow."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess
import sys
import time

from app.core.config import settings
from app.evaluation.nine_chapter_corpus import APPROVED, EXCLUDED, fingerprint, scoped_retriever, verify_scope


EXPECTED_CORPUS_SHA256 = "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8"
CHAPTER_ORDER = (1, 2, 3, 7, 9, 10, 11, 12, 13)
MODES = ("dense", "fts", "hybrid")
FROZEN_RETRIEVAL_ARTIFACTS = ("corpus.json", "environment.json", "ollama_models.json")
ANNOTATION_FIELDS = ["question_id", "question", "chapter", "candidate_id", "chunk_id", "document_id", "page",
                     "passage_text", "relevance", "reviewer_id", "rationale", "review_duration_seconds",
                     "review_timestamp_utc", "answerability", "reference_answer", "evidence_spans_json", "question_comments", "corpus_sha256"]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path, records):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_error(exc):
    """Retain useful failure text while redacting credentials from exception strings."""
    value = str(exc)
    value = re.sub(r"(?i)(://[^:/\s]+:)[^@/\s]+@", r"\1[REDACTED]@", value)
    value = re.sub(r"(?i)(password|token|secret)(\s*[=:]\s*)[^\s,;]+", r"\1\2[REDACTED]", value)
    return value[:1000]


def load_snapshot(run_dir):
    path = Path(run_dir) / "corpus.json"
    snapshot = read_json(path)
    stored = snapshot.pop("corpus_sha256", None)
    actual = fingerprint(snapshot)
    if stored != EXPECTED_CORPUS_SHA256 or actual != stored:
        raise ValueError(f"Frozen corpus fingerprint mismatch: expected {EXPECTED_CORPUS_SHA256}; stored={stored}; actual={actual}")
    verify_scope(snapshot)
    if len(snapshot["chunks"]) != 643:
        raise ValueError(f"Expected 643 frozen chunks, found {len(snapshot['chunks'])}.")
    if len(snapshot["documents"]) != 9 or any(d["embedding_dimensions"] != 1024 for d in snapshot["documents"]):
        raise ValueError("Frozen snapshot document count or embedding dimension is invalid.")
    return snapshot, stored


def corpus_report(run_dir):
    snapshot, sha = load_snapshot(run_dir)
    lengths = [len(c["content"]) for c in snapshot["chunks"]]
    ordered = sorted(lengths)
    def quantile(p):
        index = (len(ordered) - 1) * p
        lo, hi = math.floor(index), math.ceil(index)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)
    return {"run_id": Path(run_dir).name, "corpus_sha256": sha, "documents": snapshot["documents"],
            "chunk_count": len(lengths), "embedding_dimensions": 1024,
            "passage_length_chars": {"min": min(lengths), "max": max(lengths), "mean": statistics.mean(lengths),
                                     "median": statistics.median(lengths), "p90": quantile(.9)},
            "database_identity_at_freeze": snapshot["database_identity"], "migration_revision_at_freeze": snapshot["revision"],
            "pgvector_version_at_freeze": snapshot["pgvector_version"], "indexes_at_freeze": snapshot["indexes"],
            "excluded_chapters": list(EXCLUDED)}


def _source(path, statement, value, evidence="source-code default; runtime override unverified"):
    return {"value": value, "source": path, "evidence": statement}


def validate_frozen_artifacts(run_dir, dataset_path=None):
    required = [Path(run_dir) / name for name in FROZEN_RETRIEVAL_ARTIFACTS]
    if dataset_path is not None:
        required.append(Path(dataset_path))
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required research files:\n - " + "\n - ".join(missing) +
                                "\nUse the original preparation artifacts; do not regenerate frozen metadata.")


def build_system_configuration(run_dir):
    validate_frozen_artifacts(run_dir)
    report = corpus_report(run_dir)
    env = read_json(Path(run_dir) / "environment.json")
    models = read_json(Path(run_dir) / "ollama_models.json").get("models", [])
    digest_by_name = {m.get("name"): m.get("digest") for m in models}
    model_by_name = {m.get("name"): m for m in models}
    code = "backend/app/services/retrieval_service.py"
    config = "backend/app/core/config.py"
    values = {
        "dense_similarity": _source(code, "Chunk.embedding.cosine_distance(query_embedding); score=1-distance", "cosine similarity"),
        "embedding_model": _source(config, "EMBEDDING_MODEL default; frozen run environment uses model tag", env["models"]["embedding"]),
        "embedding_digest": _source("research/results/nine_science_03/ollama_models.json", "Ollama /api/tags captured in frozen run", digest_by_name.get("bge-m3:latest")),
        "embedding_model_details": _source("research/results/nine_science_03/ollama_models.json", "Ollama tag details captured in frozen run", model_by_name.get("bge-m3:latest", {}).get("details")),
        "embedding_dimensions": _source("research/results/nine_science_03/corpus.json", "frozen vectors verified at 1024 dimensions", report["embedding_dimensions"]),
        "fts_dictionary": _source("backend/app/services/retrieval_service.py; backend/alembic/versions/0010_hybrid_retrieval_fts.py", "to_tsvector and websearch_to_tsquery use literal simple config", "simple"),
        "fts_query_construction": _source(code, "websearch_to_tsquery('simple', query_text)", "websearch_to_tsquery"),
        "fts_ranking": _source(code, "ts_rank_cd(search_vector, search_query, 32), descending score then chunk ID", "ts_rank_cd normalization=32"),
        "hybrid_fusion": _source(code, "reciprocal_rank_fusion; sum 1/(rrf_k+rank); deterministic tie breaks", "RRF"),
        "rrf_k": _source(config, "RETRIEVAL_RRF_K", env["rrf_k"]),
        "candidate_multiplier": _source(config, "RETRIEVAL_CANDIDATE_MULTIPLIER; candidate_limit=max(top_k,top_k*multiplier)", env["candidate_multiplier"]),
        "candidate_depth_for_top10": _source(code, "top_k=10 and recorded multiplier=4", 40),
        "final_top_k": _source("research/experiments/rag_comparison protocol", "research run requests top_k=10", 10),
        "generation_top_k": _source(config, "RETRIEVAL_TOP_K", env["generation_top_k"]),
        "dense_relevance_threshold": _source(config, "RELEVANCE_THRESHOLD", env["thresholds"]["dense"]),
        "lexical_relevance_threshold": _source(config, "LEXICAL_RELEVANCE_THRESHOLD", env["thresholds"]["lexical"]),
        "context_min_similarity": _source(config, "CONTEXT_MIN_SIMILARITY", env["context"]["min_similarity"]),
        "context_max_similarity_drop": _source(config, "CONTEXT_MAX_SIMILARITY_DROP", env["context"]["max_similarity_drop"]),
        "context_budget_chars": _source(config, "RAG_MAX_CONTEXT_CHARS", env["context"]["max_chars"]),
        "vector_index": {"value": "No HNSW/IVFFlat vector index appears in the frozen pg_indexes evidence; runtime query plan not captured, so exact execution plan is unverified.", "source": "research/results/nine_science_03/corpus.json:indexes"},
        "generation_model": _source(config, "LLM_MODEL; frozen run Ollama tags", env["models"]["generation"]),
        "generation_digest": _source("research/results/nine_science_03/ollama_models.json", "Ollama /api/tags captured in frozen run", digest_by_name.get("llama3:8b")),
        "generation_model_details": _source("research/results/nine_science_03/ollama_models.json", "Ollama tag details captured in frozen run", model_by_name.get("llama3:8b", {}).get("details")),
        "generation_request": _source("backend/app/services/llm_service.py", "non-streaming Ollama /api/generate; only temperature is sent in options", {"stream": False, "temperature": env["temperature"], "other_generation_options": "not set in source"}),
        "generation_temperature": _source(config, "LLM_TEMPERATURE", env["temperature"]),
        "generation_timeout_seconds": _source(config, "OLLAMA_GENERATION_TIMEOUT_SECONDS", 300.0),
        "database_migration_revision": _source("research/results/nine_science_03/corpus.json", "Alembic revision observed at freeze", report["migration_revision_at_freeze"]),
        "postgres_runtime_parameters": {"value": None, "source": "not captured by frozen run; query runtime configuration from authorized host if required"},
        "chunking": {"chunk_size_chars": _source(config, "CHUNK_SIZE; source default, deployed override not captured", 1000),
                     "chunk_overlap_chars": _source(config, "CHUNK_OVERLAP; source default, deployed override not captured", 150),
                     "method": _source("backend/app/services/text_chunking.py", "page-local natural boundary chunking; page number retained", "deterministic character-based page-aware chunking")},
        "frozen_passage_length_chars": {"value": report["passage_length_chars"], "source": "research/results/nine_science_03/corpus.json:chunks[].content"},
        "database": {"identity": report["database_identity_at_freeze"], "pgvector_version": report["pgvector_version_at_freeze"], "indexes": report["indexes_at_freeze"]},
        "runtime_caveat": "Values from environment.json and Ollama tags are recorded in the frozen run. The current runtime and database have not been queried by this process."}
    return {"frozen_run_id": Path(run_dir).name, "corpus_sha256": report["corpus_sha256"], "settings": values}


def classify_question(text):
    q = text.casefold()
    if q.startswith(("why", "how does", "how do", "explain", "describe")): return "explanation (proposed lexical classification)"
    if q.startswith(("what is", "what are", "define")): return "definition (proposed lexical classification)"
    if "difference" in q or "differ" in q or "compare" in q: return "comparison (proposed lexical classification)"
    if q.startswith(("which", "name", "list")): return "recall/list (proposed lexical classification)"
    return "other (proposed lexical classification)"


def select_questions(run_dir, source_dataset, output_dir):
    snapshot, sha = load_snapshot(run_dir)
    records = read_jsonl(source_dataset)
    if len(records) != 50 or len({r["id"] for r in records}) != 50:
        raise ValueError("Source must be the existing 50 unique questions.")
    if has_duplicate_questions(records): raise ValueError("Duplicate question text detected in source dataset.")
    if any(r.get("corpus_sha256") != sha for r in records):
        raise ValueError("Question source corpus fingerprint does not match the frozen run.")
    if sum(r.get("split") == "dev" for r in records) != 18 or sum(r.get("split") == "test" for r in records) != 32:
        raise ValueError("Existing source split must remain 18 dev / 32 test.")
    allowed_docs = set(APPROVED.values())
    if any(r.get("document_id") not in allowed_docs or APPROVED.get(r.get("chapter_number")) != r.get("document_id") for r in records):
        raise ValueError("Source question lies outside approved documents.")
    selected = select_research_records(records)
    for record in selected:
        record["question_type"] = classify_question(record["question"])
        record["question_type_status"] = "proposed; human verification required"
        record["answerability_status"] = "candidate/unverified" if record.get("answerable") is None else "preserved from source; review status required"
        record["source_authorship_provenance"] = record.get("question_provenance", "not present in source")
    if len(selected) != 40 or sum(x["split"] == "test" for x in selected) != 22:
        raise ValueError("Could not construct 18-dev/22-test subset.")
    out = Path(output_dir)
    for path in (out / "questions.jsonl", out / "dataset_report.json"):
        if path.exists(): raise FileExistsError(f"Refusing to overwrite {path}")
    write_jsonl(out / "questions.jsonl", selected)
    by_chapter = {str(n): sum(r["chapter_number"] == n for r in selected) for n in CHAPTER_ORDER}
    type_counts = {}
    for item in selected: type_counts[item["question_type"]] = type_counts.get(item["question_type"], 0) + 1
    prov_counts = {}
    for item in selected:
        p = item["source_authorship_provenance"]
        prov_counts[p] = prov_counts.get(p, 0) + 1
    report = {"question_count": 40, "source_question_count": 50, "selection": "all 18 existing dev items plus deterministic round-robin 22 held-out test items across approved chapter order", "development_count": 18, "selected_test_count": 22, "authoritative_held_out_test_count": 32,
              "per_chapter": by_chapter, "question_type_proposed_counts": type_counts, "question_types_human_verified": False,
              "source_provenance_counts": prov_counts, "answerability": {"verified": sum(isinstance(r.get("answerable"), bool) and r.get("relevance_review", {}).get("status") == "approved" for r in selected), "unverified": sum(not (isinstance(r.get("answerable"), bool) and r.get("relevance_review", {}).get("status") == "approved") for r in selected)},
              "corpus_sha256": sha, "source_dataset_sha256": sha256_file(source_dataset), "output_dataset_sha256": sha256_file(out / "questions.jsonl"),
              "question_ids": [r["id"] for r in selected], "note": "This additional 40-question collection does not replace the original authoritative 32-question test set. Selected test items are held out and must not be used to tune settings."}
    write_json(out / "dataset_report.json", report)
    return report


def select_research_records(records):
    """Select all dev items plus a deterministic chapter-balanced test subset."""
    dev = [dict(r) for r in records if r["split"] == "dev"]
    tests_by_chapter = {n: [dict(r) for r in records if r["split"] == "test" and r["chapter_number"] == n] for n in CHAPTER_ORDER}
    selected_test = []
    # Balanced deterministic round-robin across chapters, preserving within-chapter source order.
    while len(selected_test) < 22:
        progressed = False
        for chapter in CHAPTER_ORDER:
            if tests_by_chapter[chapter]:
                selected_test.append(tests_by_chapter[chapter].pop(0)); progressed = True
                if len(selected_test) == 22: break
        if not progressed: break
    selected = dev + selected_test
    if len(dev) != 18 or len(selected_test) != 22: raise ValueError("Could not construct 18-dev/22-test subset.")
    return selected


def has_duplicate_questions(records):
    normalized = [" ".join(r["question"].casefold().split()) for r in records]
    return len(set(normalized)) != len(normalized)


def retrieval_schema(records, snapshot, expected_ids):
    chunks = {c["id"]: c for c in snapshot["chunks"]}
    docs = {d["id"]: d for d in snapshot["documents"]}
    if len(records) != len(expected_ids): raise ValueError("Retrieval output query count differs from selected dataset.")
    seen = set()
    for record in records:
        if record.get("question_id") not in expected_ids or record["question_id"] in seen: raise ValueError("Unknown/duplicate query ID in retrieval output.")
        seen.add(record["question_id"])
        if record.get("mode") not in MODES or not isinstance(record.get("latency_ms"), (int,float)) or record["latency_ms"] < 0: raise ValueError("Invalid retrieval mode or latency.")
        ranked = record.get("pre_gate_ranked", [])
        if len(ranked) > 10: raise ValueError("Ranked result exceeds top 10.")
        if [r["rank"] for r in ranked] != list(range(1, len(ranked)+1)): raise ValueError("Ranks must be contiguous and ordered.")
        for row in ranked:
            c = chunks.get(row.get("chunk_id"))
            if not c or c["document_id"] != row.get("document_id") or row.get("document_id") not in docs: raise ValueError("Retrieval result falls outside frozen chunks/documents.")
            if row.get("chapter") != c["chapter"] or row.get("page_number") != c["page_number"]: raise ValueError("Retrieval provenance does not match frozen chunk metadata.")
    if seen != set(expected_ids): raise ValueError("Some selected query IDs are missing.")


def pooled_candidates(mode_records, seed):
    """Union result lists and shuffle once; source provenance stays in a sidecar map."""
    candidates = {}
    for mode in MODES:
        for item in mode_records[mode]:
            cid = item["chunk_id"]
            candidates.setdefault(cid, []).append({"mode": mode, "rank": item["rank"], "scores": {
                key: item.get(key) for key in ("similarity_score", "lexical_score", "rrf_score")}})
    ids = list(candidates)
    random.Random(seed).shuffle(ids)
    return [(f"c{index:03d}", cid) for index, cid in enumerate(ids, 1)], candidates


async def execute_retrieval(run_dir, dataset_path, output_dir):
    validate_frozen_artifacts(run_dir, dataset_path)
    targets = [Path(output_dir) / "runs" / f"{mode}.json" for mode in MODES]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError("Refusing to overwrite retrieval outputs: " + ", ".join(existing))
    configuration = build_system_configuration(run_dir)
    from dataclasses import asdict
    from app.evaluation.metrics import evaluate_retrieval_relevance
    from app.services.context_selection import select_context_chunks
    from app.services.embedding_service import embedding_service
    from app.services.grounded_context import build_grounded_context
    from app.services.retrieval_service import retrieval_service
    snapshot, sha = load_snapshot(run_dir)
    from scripts.nine_chapter_research import snapshot as read_live_snapshot
    live = read_live_snapshot()
    if fingerprint(live) != sha:
        raise ValueError("Live database snapshot differs from frozen nine_science_03 corpus; retrieval stopped.")
    examples = read_jsonl(dataset_path)
    if len(examples) != 40 or len({e["id"] for e in examples}) != 40 or any(e.get("corpus_sha256") != sha for e in examples):
        raise ValueError("Expected the validated 40-question subset for the same frozen corpus.")
    retrieve = scoped_retriever(snapshot, retrieval_service.retrieve_chunks)
    all_results = {mode: [] for mode in MODES}
    randomizer = random.Random(20261030)
    for example in examples:
        embedding_started = time.monotonic_ns()
        try:
            embedding = await embedding_service.get_embedding(example["question"])
            embed_ms = (time.monotonic_ns() - embedding_started) / 1_000_000
        except Exception as exc:
            embed_ms = (time.monotonic_ns() - embedding_started) / 1_000_000
            for mode in MODES:
                all_results[mode].append({"question_id": example["id"], "mode": mode, "status": "failed",
                    "error_type": type(exc).__name__, "error": safe_error(exc), "embedding_latency_ms": embed_ms,
                    "latency_ms": 0.0, "pre_gate_ranked": [], "post_gate": {"accepted": False, "evidence": []}})
            continue
        mode_order = list(MODES)
        randomizer.shuffle(mode_order)
        for mode in mode_order:
            started = time.monotonic_ns()
            backend_mode = "lexical" if mode == "fts" else mode
            try:
                retrieved = await retrieve(embedding if mode != "fts" else [], query_text=example["question"], mode=backend_mode,
                    top_k=10, candidate_multiplier=settings.RETRIEVAL_CANDIDATE_MULTIPLIER, rrf_k=settings.RETRIEVAL_RRF_K)
                latency_ms = (time.monotonic_ns() - started) / 1_000_000
                chunks = [asdict(item) for item in retrieved]
                if len(chunks) > 10: raise ValueError("Backend returned more than top 10 results.")
                accepted, dense_score, lexical_score = evaluate_retrieval_relevance(chunks,
                    dense_threshold=settings.RELEVANCE_THRESHOLD, lexical_threshold=settings.LEXICAL_RELEVANCE_THRESHOLD)
                evidence = []
                if accepted:
                    chosen = select_context_chunks(chunks, minimum_similarity=settings.CONTEXT_MIN_SIMILARITY,
                        maximum_similarity_drop=settings.CONTEXT_MAX_SIMILARITY_DROP)
                    _rendered, chosen = build_grounded_context(chosen, settings.RAG_MAX_CONTEXT_CHARS)
                    evidence = [{"chunk_id": c["id"], "document_id": c["document_id"], "page_number": c["page_number"],
                                 "chapter": c["chapter"], "similarity_score": c["similarity_score"],
                                 "lexical_score": c["lexical_score"], "rrf_score": c["rrf_score"]} for c in chosen]
                ranked = [{"rank": rank, "chunk_id": c["id"], "document_id": c["document_id"], "chapter": c["chapter"],
                           "page_number": c["page_number"], "chunk_index": c["chunk_index"],
                           "similarity_score": c["similarity_score"], "lexical_score": c["lexical_score"],
                           "vector_rank": c["vector_rank"], "lexical_rank": c["lexical_rank"], "rrf_score": c["rrf_score"]}
                          for rank, c in enumerate(chunks, 1)]
                all_results[mode].append({"question_id": example["id"], "question": example["question"], "mode": mode,
                    "status": "success", "embedding_latency_ms": round(embed_ms, 3), "latency_ms": round(latency_ms, 3),
                    "pre_gate_ranked": ranked, "post_gate": {"accepted": accepted, "max_dense_score": dense_score,
                    "max_lexical_score": lexical_score, "evidence": evidence}})
            except Exception as exc:
                latency_ms = (time.monotonic_ns() - started) / 1_000_000
                all_results[mode].append({"question_id": example["id"], "question": example["question"], "mode": mode,
                    "status": "failed", "error_type": type(exc).__name__, "error": safe_error(exc),
                    "embedding_latency_ms": round(embed_ms, 3), "latency_ms": round(latency_ms, 3),
                    "pre_gate_ranked": [], "post_gate": {"accepted": False, "evidence": []}})
    if fingerprint(read_live_snapshot()) != sha:
        raise ValueError("Live database changed during retrieval; discard output.")
    out = Path(output_dir)
    targets = [out / "runs" / f"{mode}.json" for mode in MODES]
    existing = [str(path) for path in targets if path.exists()]
    if existing: raise FileExistsError("Refusing to overwrite retrieval outputs: " + ", ".join(existing))
    for mode, records in all_results.items():
        retrieval_schema(records, snapshot, {e["id"] for e in examples})
        target = out / "runs" / f"{mode}.json"
        successes = sum(r["status"] == "success" for r in records)
        payload = {"run_id": "nine_science_03", "corpus_sha256": sha, "dataset_sha256": sha256_file(dataset_path),
            "mode": mode, "top_k": 10, "candidate_depth": 40, "retrieval_settings": configuration["settings"],
            "warmup": "No explicit warmup; model/service cache state not controlled. Three conditions randomized per question with seed 20261030.",
            "execution": {"queries": len(records), "successes": successes, "failures": len(records)-successes,
                          "hardware": platform.platform(), "python": platform.python_version(),
                          "finished_at_utc": datetime.now(timezone.utc).isoformat()}, "queries": records}
        write_json(target, payload)
    return {m: {"queries": len(v), "successes": sum(x["status"] == "success" for x in v),
                "failures": sum(x["status"] != "success" for x in v)} for m, v in all_results.items()}


def make_pool(run_dir, dataset_path, run_files, output_dir, seed):
    snapshot, sha = load_snapshot(run_dir)
    examples = read_jsonl(dataset_path)
    if len(examples) != 40: raise ValueError("Pooling expects exactly 40 selected questions.")
    by_mode = {}
    for mode in MODES:
        payload = read_json(run_files[mode])
        if payload.get("corpus_sha256") != sha or payload.get("mode") != mode: raise ValueError(f"{mode}: corpus/mode mismatch.")
        if payload.get("dataset_sha256") != sha256_file(dataset_path): raise ValueError(f"{mode}: source question dataset hash mismatch.")
        records = payload.get("queries", [])
        retrieval_schema(records, snapshot, {e["id"] for e in examples})
        questions_by_id = {e["id"]: e["question"] for e in examples}
        if any(r.get("question") != questions_by_id[r["question_id"]] for r in records): raise ValueError(f"{mode}: query text differs from selected dataset.")
        if any(r["status"] != "success" for r in records): raise ValueError(f"{mode}: failed queries prevent annotation pool creation.")
        by_mode[mode] = {r["question_id"]: r for r in records}
    chunk_map = {c["id"]: c for c in snapshot["chunks"]}
    docs = {d["id"]: d for d in snapshot["documents"]}
    pool_rows, origin_map = [], {}
    for example in examples:
        qid = example["id"]
        stable_seed = seed ^ int.from_bytes(hashlib.sha256(qid.encode("utf-8")).digest()[:8], "big")
        candidate_order, candidates = pooled_candidates({mode: by_mode[mode][qid]["pre_gate_ranked"] for mode in MODES}, stable_seed)
        for candidate_id_suffix, chunk_id in candidate_order:
            candidate_id = f"{qid}-{candidate_id_suffix}"
            chunk = chunk_map[chunk_id]
            row = {"question_id": qid, "question": example["question"], "chapter": chunk["chapter"],
                   "candidate_id": candidate_id, "chunk_id": chunk_id, "document_id": chunk["document_id"],
                   "page": chunk["page_number"], "passage_text": chunk["content"], "relevance": "", "reviewer_id": "",
                   "rationale": "", "review_duration_seconds": "", "answerability": "", "reference_answer": "",
                   "evidence_spans_json": "", "question_comments": "", "corpus_sha256": sha}
            pool_rows.append(row)
            origin_map[candidate_id] = {"question_id": qid, "chunk_id": chunk_id, "document_id": chunk["document_id"],
                                        "chapter_number": example["chapter_number"], "split": example["split"],
                                        "question": example["question"], "source_retrievers": candidates[chunk_id]}
    out = Path(output_dir)
    worksheets_dir, map_path = out / "annotations", out / "annotations" / "pool_origin_mapping.json"
    if map_path.exists(): raise FileExistsError(f"Refusing to overwrite {map_path}")
    worksheets_dir.mkdir(parents=True, exist_ok=True)
    for reviewer in (1, 2):
        path = worksheets_dir / f"reviewer_{reviewer}.csv"
        with path.open("x", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=ANNOTATION_FIELDS)
            writer.writeheader(); writer.writerows(pool_rows)
    write_json(map_path, {"seed": seed, "corpus_sha256": sha, "rows": origin_map})
    return {"pooled_pairs": len(pool_rows), "unique_chunks": len({r["chunk_id"] for r in pool_rows}),
            "worksheet_1": str(worksheets_dir / "reviewer_1.csv"), "worksheet_2": str(worksheets_dir / "reviewer_2.csv"),
            "origin_mapping": str(map_path)}


def _answerability_value(text, qid):
    value = (text or "").strip().casefold()
    if value not in {"true", "false"}: raise ValueError(f"{qid}: explicit question-level answerability is required (true/false).")
    return value == "true"


def _spans(text, qid):
    try: value = json.loads(text) if (text or "").strip() else []
    except json.JSONDecodeError as exc: raise ValueError(f"{qid}: evidence_spans_json must be valid JSON.") from exc
    if not isinstance(value, list): raise ValueError(f"{qid}: evidence spans must be a JSON list.")
    return value


def _review_file(path, expected_rows, snapshot, expected_sha):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle: rows = list(csv.DictReader(handle))
    expected_by_id = {r["candidate_id"]: r for r in expected_rows}
    if len(rows) != len(expected_rows) or {r.get("candidate_id") for r in rows} != set(expected_by_id):
        raise ValueError(f"{path}: missing, duplicate, or unexpected candidate rows.")
    identities = set(); by_candidate = {}; questions = {}
    frozen_chunks = {c["id"]: c for c in snapshot["chunks"]}
    for row in rows:
        expected = expected_by_id[row["candidate_id"]]
        for field in ("question_id", "question", "chunk_id", "document_id", "chapter", "page", "corpus_sha256"):
            if row.get(field) != str(expected.get(field)): raise ValueError(f"{row.get('candidate_id')}: immutable {field} changed.")
        if row.get("corpus_sha256") != expected_sha: raise ValueError("Reviewer worksheet corpus fingerprint mismatch.")
        reviewer = (row.get("reviewer_id") or "").strip()
        if not reviewer: raise ValueError("Reviewer ID is required on every row.")
        identities.add(reviewer)
        if row.get("relevance") not in {"0", "1"}: raise ValueError(f"{row['candidate_id']}: relevance must be explicit 0 or 1.")
        if not (row.get("rationale") or "").strip(): raise ValueError(f"{row['candidate_id']}: rationale is required.")
        duration = (row.get("review_duration_seconds") or "").strip()
        if duration:
            try: seconds = float(duration)
            except ValueError as exc: raise ValueError(f"{row['candidate_id']}: invalid review duration.") from exc
            if not math.isfinite(seconds) or seconds <= 0: raise ValueError(f"{row['candidate_id']}: duration must be positive finite seconds.")
            row["_duration"] = seconds
        timestamp = (row.get("review_timestamp_utc") or "").strip()
        if timestamp:
            try: parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc: raise ValueError(f"{row['candidate_id']}: invalid ISO 8601 review timestamp.") from exc
            if parsed_timestamp.tzinfo is None: raise ValueError(f"{row['candidate_id']}: review timestamp must include a timezone.")
        qid = row["question_id"]
        answerable = _answerability_value(row.get("answerability"), qid)
        spans = _spans(row.get("evidence_spans_json"), qid)
        if answerable and (not (row.get("reference_answer") or "").strip() or not spans):
            raise ValueError(f"{qid}: answerable questions require reference answer and evidence spans.")
        positives = [r for r in rows if r.get("question_id") == qid and r.get("relevance") == "1"]
        if not answerable and positives: raise ValueError(f"{qid}: unanswerable judgment conflicts with positive sufficient-evidence labels.")
        if answerable and not positives: raise ValueError(f"{qid}: answerable question needs a positively judged pooled evidence passage.")
        chunks_for_question = {x["candidate_id"]: x for x in rows if x.get("question_id") == qid}
        positive_chunk_ids = {x["chunk_id"] for x in positives}
        for span in spans:
            if not isinstance(span, dict): raise ValueError(f"{qid}: evidence span must be an object.")
            chunk = frozen_chunks.get(span.get("passage_id"))
            if not chunk or span.get("passage_id") not in {x["chunk_id"] for x in chunks_for_question.values()} or span.get("passage_id") not in positive_chunk_ids or not isinstance(span.get("start_char"), int) or not isinstance(span.get("end_char"), int) or not 0 <= span["start_char"] < span["end_char"] <= len(chunk["content"]):
                raise ValueError(f"{qid}: evidence span is outside a frozen pooled passage.")
        qvalue = {"answerable": answerable, "reference_answer": (row.get("reference_answer") or "").strip(),
                  "evidence_spans": spans}
        if qid in questions and questions[qid] != qvalue: raise ValueError(f"{qid}: repeated question-level fields must be identical within reviewer worksheet.")
        questions[qid] = qvalue
        by_candidate[row["candidate_id"]] = int(row["relevance"])
    if len(identities) != 1: raise ValueError("Each reviewer file must use exactly one reviewer ID.")
    return next(iter(identities)), by_candidate, questions, [r["_duration"] for r in rows if "_duration" in r]


def cohen_kappa(left, right):
    if not left or len(left) != len(right): raise ValueError("Kappa requires equal, nonempty paired judgments.")
    n = len(left); observed = sum(a == b for a, b in zip(left, right)) / n
    labels = set(left) | set(right)
    expected = sum((sum(v == label for v in left) / n) * (sum(v == label for v in right) / n) for label in labels)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def require_distinct_reviewers(reviewer1_id, reviewer2_id):
    if not reviewer1_id or not reviewer2_id or reviewer1_id == reviewer2_id:
        raise ValueError("Reviewer identities must be present and distinct.")


def validate_adjudications(required_disputes, rows):
    """Check explicit judgment, adjudicator attribution, rationale and date for each dispute."""
    seen = set(); finals = {}
    for row in rows:
        kind = row.get("disagreement_type")
        key = (kind, row.get("candidate_id") if kind == "relevance" else row.get("question_id"))
        if key not in required_disputes or key in seen: raise ValueError("Adjudication row is unexpected or duplicated.")
        seen.add(key)
        if not (row.get("adjudicator_id") or "").strip() or not (row.get("adjudication_rationale") or "").strip():
            raise ValueError("Adjudicator identity and rationale are required.")
        try: datetime.strptime(row.get("adjudication_date", ""), "%Y-%m-%d")
        except ValueError as exc: raise ValueError("Adjudication date must use YYYY-MM-DD.") from exc
        if kind == "relevance":
            if row.get("final_relevance") not in {"0", "1"}: raise ValueError("Final relevance must be explicit 0 or 1.")
            finals[key] = int(row["final_relevance"])
        elif kind == "question_level":
            finals[key] = row
        else: raise ValueError("Unknown disagreement type.")
    if seen != set(required_disputes): raise ValueError("Every disagreement requires explicit adjudication.")
    return finals


def write_gold_artifacts(gold, metadata, gold_path):
    gold_path = Path(gold_path)
    metadata_path = gold_path.with_name("gold_metadata.json")
    if gold_path.exists() or metadata_path.exists(): raise FileExistsError(f"Refusing to overwrite gold artifact or metadata: {gold_path}")
    write_json(gold_path, gold)
    write_json(metadata_path, metadata)


def import_reviews(run_dir, pool_mapping, reviewer1, reviewer2, disagreement_out, summary_out):
    snapshot, sha = load_snapshot(run_dir)
    mapping = read_json(pool_mapping)
    if mapping["corpus_sha256"] != sha: raise ValueError("Pool mapping fingerprint mismatch.")
    # The shuffled order and source IDs come from the worksheet themselves; mapping defines expected candidates.
    expected_rows = []
    for candidate_id, value in mapping["rows"].items():
        expected_rows.append({"candidate_id": candidate_id, **value})
    # Review field validation uses the pool mapping and frozen snapshot as immutable metadata.
    chunks = {c["id"]: c for c in snapshot["chunks"]}
    documents = {d["id"]: d for d in snapshot["documents"]}
    for item in expected_rows:
        c = chunks.get(item["chunk_id"])
        if not c or item["document_id"] not in documents or c["document_id"] != item["document_id"]:
            raise ValueError("Pool mapping references content outside frozen corpus.")
    for item in expected_rows:
        c = chunks[item["chunk_id"]]
        item.update({"question": item["question"], "chapter": c["chapter"], "page": str(c["page_number"]), "corpus_sha256": sha})
    id1, labels1, questions1, durations1 = _review_file(reviewer1, expected_rows, snapshot, sha)
    id2, labels2, questions2, durations2 = _review_file(reviewer2, expected_rows, snapshot, sha)
    require_distinct_reviewers(id1, id2)
    if set(questions1) != set(questions2): raise ValueError("Reviewers must cover identical question IDs.")
    disagreements = []
    for cid in sorted(labels1):
        if labels1[cid] != labels2[cid]:
            m = mapping["rows"][cid]
            disagreements.append({"disagreement_type": "relevance", "question_id": m["question_id"], "candidate_id": cid,
                "chunk_id": m["chunk_id"], "reviewer_1_label": labels1[cid], "reviewer_2_label": labels2[cid],
                "final_relevance": "", "final_answerability": "", "final_reference_answer": "", "final_evidence_spans_json": "",
                "adjudicator_id": "", "adjudication_rationale": "", "adjudication_date": ""})
    for qid in sorted(questions1):
        if questions1[qid] != questions2[qid]:
            disagreements.append({"disagreement_type": "question_level", "question_id": qid, "candidate_id": "", "chunk_id": "",
                "reviewer_1_label": "", "reviewer_2_label": "", "final_relevance": "",
                "reviewer_1_answerability": str(questions1[qid]["answerable"]).lower(), "reviewer_2_answerability": str(questions2[qid]["answerable"]).lower(),
                "reviewer_1_reference_answer": questions1[qid]["reference_answer"], "reviewer_2_reference_answer": questions2[qid]["reference_answer"],
                "reviewer_1_evidence_spans_json": json.dumps(questions1[qid]["evidence_spans"], ensure_ascii=False),
                "reviewer_2_evidence_spans_json": json.dumps(questions2[qid]["evidence_spans"], ensure_ascii=False),
                "final_answerability": "", "final_reference_answer": "", "final_evidence_spans_json": "",
                "adjudicator_id": "", "adjudication_rationale": "", "adjudication_date": ""})
    disagreement_out = Path(disagreement_out); summary_out = Path(summary_out)
    if disagreement_out.exists() or summary_out.exists(): raise FileExistsError("Refusing to overwrite annotation evidence.")
    fields = list(dict.fromkeys(k for row in disagreements for k in row)) or ["disagreement_type", "question_id", "candidate_id", "chunk_id", "reviewer_1_label", "reviewer_2_label", "final_relevance", "final_answerability", "final_reference_answer", "final_evidence_spans_json", "adjudicator_id", "adjudication_rationale", "adjudication_date"]
    disagreement_out.parent.mkdir(parents=True, exist_ok=True)
    with disagreement_out.open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(disagreements)
    n = len(labels1); agree = sum(labels1[c] == labels2[c] for c in labels1)
    summary = {"corpus_sha256": sha, "reviewer_1": id1, "reviewer_2": id2,
        "independently_labelled_question_passage_pairs": n, "positive_labels": {id1: sum(labels1.values()), id2: sum(labels2.values())},
        "negative_labels": {id1: n-sum(labels1.values()), id2: n-sum(labels2.values())}, "raw_agreement": agree/n if n else None,
        "cohen_kappa": cohen_kappa(list(labels1.values()), list(labels2.values())), "relevance_disagreements": sum(labels1[c] != labels2[c] for c in labels1),
        "question_level_disagreements": sum(1 for r in disagreements if r["disagreement_type"] == "question_level"),
        "median_review_seconds": {id1: statistics.median(durations1) if durations1 else None, id2: statistics.median(durations2) if durations2 else None},
        "disagreements_csv": str(disagreement_out)}
    write_json(summary_out, summary)
    return summary


def adjudicate_export(run_dir, dataset_path, pool_mapping, reviewer1, reviewer2, adjudications_csv, gold_path):
    snapshot, sha = load_snapshot(run_dir)
    mapping = read_json(pool_mapping)
    if mapping["corpus_sha256"] != sha: raise ValueError("Pool mapping fingerprint mismatch.")
    # Validate both completed independent files and use their shared immutable question/candidate metadata.
    with Path(reviewer1).open("r", newline="", encoding="utf-8-sig") as h1: rows1 = list(csv.DictReader(h1))
    with Path(reviewer2).open("r", newline="", encoding="utf-8-sig") as h2: rows2 = list(csv.DictReader(h2))
    by1 = {r.get("candidate_id"): r for r in rows1}; by2 = {r.get("candidate_id"): r for r in rows2}
    if set(by1) != set(mapping["rows"]) or set(by2) != set(mapping["rows"]): raise ValueError("Reviewer worksheet candidate set differs from frozen pool.")
    # Re-run full reviewer validation using frozen row metadata.
    chunks = {c["id"]: c for c in snapshot["chunks"]}
    expected_rows = []
    for cid, m in mapping["rows"].items():
        a = by1[cid]; c = chunks[m["chunk_id"]]
        expected_rows.append({"candidate_id": cid, "question_id": m["question_id"], "chunk_id": m["chunk_id"], "document_id": m["document_id"],
            "question": m["question"], "chapter": c["chapter"], "page": str(c["page_number"]), "corpus_sha256": sha})
    id1, labels1, questions1, _ = _review_file(reviewer1, expected_rows, snapshot, sha)
    id2, labels2, questions2, _ = _review_file(reviewer2, expected_rows, snapshot, sha)
    require_distinct_reviewers(id1, id2)
    required_disputes = {}
    for cid in labels1:
        if labels1[cid] != labels2[cid]: required_disputes[("relevance", cid)] = None
    for qid in questions1:
        if questions1[qid] != questions2[qid]: required_disputes[("question_level", qid)] = None
    with Path(adjudications_csv).open("r", newline="", encoding="utf-8-sig") as handle: adjudications = list(csv.DictReader(handle))
    finals = validate_adjudications(required_disputes, adjudications)
    for key, row in finals.items():
        if key[0] == "question_level":
            final_answerable = _answerability_value(row.get("final_answerability"), key[1])
            spans = _spans(row.get("final_evidence_spans_json"), key[1])
            answer = (row.get("final_reference_answer") or "").strip()
            if final_answerable and (not answer or not spans): raise ValueError("Adjudicated answerable question requires answer and evidence spans.")
            for span in spans:
                c = chunks.get(span.get("passage_id")) if isinstance(span, dict) else None
                if not c or not isinstance(span.get("start_char"), int) or not isinstance(span.get("end_char"), int) or not 0 <= span["start_char"] < span["end_char"] <= len(c["content"]): raise ValueError("Adjudicated evidence span is outside frozen corpus.")
            required_disputes[key] = {"answerable": final_answerable, "reference_answer": answer, "evidence_spans": spans,
                                      "adjudicator_id": row["adjudicator_id"].strip(), "rationale": row["adjudication_rationale"].strip(), "date": row["adjudication_date"]}
        else:
            required_disputes[key] = finals[key]
    source_questions = read_jsonl(dataset_path)
    if len(source_questions) != 40: raise ValueError("Gold export requires the preserved 40-question collection.")
    question_rows = {r["id"]: r for r in source_questions}
    expected_qids = {v["question_id"] for v in mapping["rows"].values()}
    if set(question_rows) != expected_qids or any(question_rows[qid].get("corpus_sha256") != sha for qid in question_rows):
        raise ValueError("Selected question dataset does not match the frozen pool question IDs/fingerprint.")
    for cid, item in mapping["rows"].items():
        question = question_rows[item["question_id"]]
        if item.get("question") != question["question"] or item.get("document_id") != question["document_id"] or item.get("chapter_number") != question["chapter_number"] or item.get("split") != question["split"]:
            raise ValueError("Pool mapping question metadata differs from the selected frozen question dataset.")
    gold = []
    for qid, base in question_rows.items():
        candidate_ids = [cid for cid, m in mapping["rows"].items() if m["question_id"] == qid]
        rel = {}
        for cid in candidate_ids:
            rel[cid] = required_disputes[("relevance", cid)] if ("relevance", cid) in required_disputes else labels1[cid]
        question = questions1[qid]
        if ("question_level", qid) in required_disputes:
            question = required_disputes[("question_level", qid)]
        answerable = question["answerable"]
        positives = [mapping["rows"][cid]["chunk_id"] for cid, label in rel.items() if label == 1]
        if answerable and not positives: raise ValueError(f"{qid}: answerable gold record has no positive pooled chunks.")
        if not answerable and positives: raise ValueError(f"{qid}: unanswerable gold record has positive chunks.")
        if answerable:
            for span in question["evidence_spans"]:
                if span.get("passage_id") not in positives: raise ValueError(f"{qid}: question evidence span must refer to a positive pooled chunk.")
        gold.append({"id": qid, "question": base["question"], "answerable": answerable,
            "gold_passage_ids": positives, "judged_passage_ids": [mapping["rows"][cid]["chunk_id"] for cid in candidate_ids],
            "relevance_judgments": {mapping["rows"][cid]["chunk_id"]: rel[cid] for cid in candidate_ids},
            "reference_answer": question["reference_answer"] or None, "evidence_spans": question["evidence_spans"],
            "split": base["split"], "chapter_number": base["chapter_number"], "document_id": base["document_id"],
            "corpus_sha256": sha, "question_type": base.get("question_type"),
            "question_type_status": base.get("question_type_status"), "gold_provenance": "two independent human judgments; disagreements explicitly adjudicated"})
    write_gold_artifacts(gold, {"corpus_sha256": sha, "questions": len(gold), "pool_seed": mapping["seed"],
        "unjudged_passages_are_not_negative": True, "retrieval_qrels": "Only pooled passages are judged; unpooled chunks are unknown."}, gold_path)
    return {"gold_path": str(gold_path), "questions": len(gold), "corpus_sha256": sha, "adjudicated_disagreements": len(required_disputes)}


def manifest(run_dir, experiment_dir, source_dataset, subset_dataset):
    config_path = Path(experiment_dir) / "system_configuration.json"
    if not config_path.exists(): raise ValueError("Run inspect before manifest generation.")
    git_revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    git_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=False)
    files = {}
    for path in sorted(Path(experiment_dir).rglob("*")):
        if path.is_file() and path.name not in {"experiment_manifest.json", "execution.log"}:
            files[str(path.relative_to(Path(experiment_dir)))] = sha256_file(path)
    source_files = ("app/services/retrieval_service.py", "app/core/config.py", "app/services/text_chunking.py",
                    "app/evaluation/metrics.py", "scripts/rag_comparison.py")
    code_hashes = {path: sha256_file(path) for path in source_files if Path(path).is_file()}
    dataset = read_json(Path(experiment_dir) / "datasets" / "dataset_report.json")
    result_files = {}
    for mode in MODES:
        result_path = Path(experiment_dir) / "runs" / f"{mode}.json"
        if result_path.exists():
            evidence = read_json(result_path).get("execution", {})
            result_files[mode] = {"status": "executed", "queries": evidence.get("queries"), "successes": evidence.get("successes"), "failures": evidence.get("failures"), "sha256": sha256_file(result_path)}
        else:
            result_files[mode] = {"status": "not executed; authorized running host stack required"}
    annotations = Path(experiment_dir) / "annotations"
    return {"experiment": "RAG dense vs FTS vs hybrid; Part 1", "preregistered": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "frozen_run_id": Path(run_dir).name,
        "corpus_sha256": load_snapshot(run_dir)[1], "git_commit": git_revision.stdout.strip() if git_revision.returncode == 0 else None,
        "working_tree_status": git_status.stdout, "selected_question_ids": dataset["question_ids"],
        "source_dataset_sha256": sha256_file(source_dataset), "selected_dataset_sha256": sha256_file(subset_dataset),
        "research_code_sha256": code_hashes,
        "retrieval_settings": read_json(config_path)["settings"], "random_seed": 20261030,
        "software": {"python": platform.python_version(), "platform": platform.platform(), "cpu_count": os.cpu_count()},
        "hardware": "host GPU/CPU and database settings require authorized host runtime inspection; not inferred",
        "execution_status": {"dense": result_files["dense"], "fts": result_files["fts"], "hybrid": result_files["hybrid"],
                             "reviewer_worksheets": "generated; pending human review" if (annotations / "reviewer_1.csv").exists() and (annotations / "reviewer_2.csv").exists() else "not generated; retrieval pool unavailable",
                             "adjudication": "gold exported" if (Path(experiment_dir) / "gold.json").exists() else "not completed"},
        "artifact_paths": sorted(files), "artifact_sha256": files, "note": "No preregistration claim; manifest records execution evidence as it becomes available."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--run-dir", required=True); inspect.add_argument("--output", required=True)
    inspect.add_argument("--refresh", action="store_true")
    select = sub.add_parser("select-dataset")
    select.add_argument("--run-dir", required=True); select.add_argument("--source-dataset", required=True); select.add_argument("--output-dir", required=True)
    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("--run-dir", required=True); retrieve.add_argument("--dataset", required=True); retrieve.add_argument("--output-dir", required=True)
    pool = sub.add_parser("pool")
    pool.add_argument("--run-dir", required=True); pool.add_argument("--dataset", required=True); pool.add_argument("--runs-dir", required=True); pool.add_argument("--output-dir", required=True); pool.add_argument("--seed", type=int, default=20261030)
    reviews = sub.add_parser("import-reviews")
    reviews.add_argument("--run-dir", required=True); reviews.add_argument("--pool-mapping", required=True); reviews.add_argument("--reviewer-1", required=True); reviews.add_argument("--reviewer-2", required=True); reviews.add_argument("--disagreements", required=True); reviews.add_argument("--summary", required=True)
    gold = sub.add_parser("export-gold")
    gold.add_argument("--run-dir", required=True); gold.add_argument("--dataset", required=True); gold.add_argument("--pool-mapping", required=True); gold.add_argument("--reviewer-1", required=True); gold.add_argument("--reviewer-2", required=True); gold.add_argument("--adjudications", required=True); gold.add_argument("--output", required=True)
    manifest_parser = sub.add_parser("manifest")
    manifest_parser.add_argument("--run-dir", required=True); manifest_parser.add_argument("--experiment-dir", required=True); manifest_parser.add_argument("--source-dataset", required=True); manifest_parser.add_argument("--subset-dataset", required=True)
    manifest_parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        report = corpus_report(args.run_dir)
        config = build_system_configuration(args.run_dir)
        report_path = Path(args.output).with_name("frozen_corpus_report.json")
        if (Path(args.output).exists() or report_path.exists()) and not args.refresh:
            raise FileExistsError(f"Refusing to overwrite inspection artifacts; pass --refresh to update: {args.output}")
        write_json(args.output, config)
        write_json(report_path, report)
        print(json.dumps(report, indent=2))
    elif args.command == "select-dataset": print(json.dumps(select_questions(args.run_dir, args.source_dataset, args.output_dir), indent=2))
    elif args.command == "retrieve": print(json.dumps(asyncio.run(execute_retrieval(args.run_dir, args.dataset, args.output_dir)), indent=2))
    elif args.command == "pool": print(json.dumps(make_pool(args.run_dir, args.dataset, {m: Path(args.runs_dir)/f"{m}.json" for m in MODES}, args.output_dir, args.seed), indent=2))
    elif args.command == "import-reviews": print(json.dumps(import_reviews(args.run_dir, args.pool_mapping, args.reviewer_1, args.reviewer_2, args.disagreements, args.summary), indent=2))
    elif args.command == "export-gold": print(json.dumps(adjudicate_export(args.run_dir, args.dataset, args.pool_mapping, args.reviewer_1, args.reviewer_2, args.adjudications, args.output), indent=2))
    else:
        value = manifest(args.run_dir, args.experiment_dir, args.source_dataset, args.subset_dataset)
        target = Path(args.experiment_dir)/"experiment_manifest.json"
        if target.exists() and not args.refresh: raise FileExistsError(f"Refusing to overwrite {target}; pass --refresh to update the manifest after new runs.")
        write_json(target, value)
        print(target)


if __name__ == "__main__":
    main()

