"""Read-only DB research workflow: freeze, evaluate reviewed questions, report."""
import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from uuid import UUID

from sqlalchemy import select, text
from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.evaluation.nine_chapter_corpus import APPROVED, EXCLUDED, fingerprint, validate_judgments, scoped_retriever
from app.evaluation.retrieval_benchmark import RetrievalBenchmark, load_benchmark_dataset, percentile
from app.evaluation.review_dataset import export_csv_report
from app.services.embedding_service import embedding_service
from app.services.retrieval_service import retrieval_service


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def snapshot():
    """Single repeatable-read transaction, including vectors in the fingerprint."""
    with SyncSessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        identity = list(db.execute(text("SELECT current_database(), current_user")).one())
        docs = db.scalars(select(Document).where(Document.id.in_([UUID(v) for v in APPROVED.values()]))).all()
        if len(docs) != 9 or any(d.processing_status != "completed" for d in docs):
            raise ValueError("All nine allowlisted documents must exist and be completed.")
        rows = db.scalars(select(Chunk).where(Chunk.document_id.in_([UUID(v) for v in APPROVED.values()])).order_by(Chunk.id)).all()
        if len(rows) != 643:
            raise ValueError(f"Expected the approved 643-chunk corpus; found {len(rows)}. Review scope before refreezing.")
        chunks = []
        for c in rows:
            if c.embedding is None or len(c.embedding) != 1024 or c.page_number is None or c.page_number < 1:
                raise ValueError(f"Invalid embedding or page provenance for chunk {c.id}.")
            chunks.append({"id": str(c.id), "document_id": str(c.document_id), "chapter": c.chapter,
                           "page_number": c.page_number, "chunk_index": c.chunk_index, "content": c.content,
                           "embedding_sha256": fingerprint([float(v) for v in c.embedding])})
        documents = [{"chapter_number": n, "id": did, "title": next(d.title for d in docs if str(d.id) == did),
                      "chunks": sum(c["document_id"] == did for c in chunks), "embedding_dimensions": 1024} for n, did in APPROVED.items()]
        if any(not d["chunks"] for d in documents):
            raise ValueError("An approved chapter has no chunks.")
        revision = list(db.scalars(text("SELECT version_num FROM alembic_version")))
        if revision != ["0010_hybrid_retrieval_fts"]:
            raise ValueError("Database is not at the approved migration revision 0010.")
        indexes = sorted(db.scalars(text("SELECT indexdef FROM pg_indexes WHERE tablename='chunks'")))
        extension = db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        if not extension or not any("ix_chunks_content_fts" in i and "gin" in i.lower() for i in indexes):
            raise ValueError("pgvector or the FTS GIN index is missing.")
    return {"approved": {str(k): v for k, v in APPROVED.items()}, "excluded_chapters": list(EXCLUDED),
            "database_identity": identity, "revision": revision, "pgvector_version": extension,
            "indexes": indexes, "documents": documents, "chunks": chunks}


def freeze(args):
    if settings.LLM_MODEL != "llama3:8b" or settings.EMBEDDING_MODEL.split(":")[0] != "bge-m3":
        raise ValueError("This protocol requires llama3:8b and bge-m3.")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    value = snapshot()
    value["corpus_sha256"] = fingerprint(value)
    save(out / "corpus.json", value)
    implementation = out / "implementation"
    implementation.mkdir()
    for source_path in ("app/graph/nodes.py", "app/services/grounded_context.py", "app/services/context_selection.py",
                        "app/services/retrieval_service.py", "app/evaluation/retrieval_benchmark.py",
                        "app/evaluation/nine_chapter_corpus.py", "scripts/nine_chapter_research.py"):
        source = Path(source_path)
        (implementation / source_path.replace("/", "__")).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False) if __import__("shutil").which("git") else None
    save(out / "environment.json", {"python": platform.python_version(), "platform": platform.platform(),
         "cpu_count": os.cpu_count(), "code_revision": revision.stdout.strip() if revision and revision.returncode == 0 else "record host git revision",
         "models": {"generation": settings.LLM_MODEL, "embedding": settings.EMBEDDING_MODEL},
         "temperature": settings.LLM_TEMPERATURE, "rrf_k": settings.RETRIEVAL_RRF_K,
         "candidate_multiplier": settings.RETRIEVAL_CANDIDATE_MULTIPLIER,
         "thresholds": {"dense": settings.RELEVANCE_THRESHOLD, "lexical": settings.LEXICAL_RELEVANCE_THRESHOLD},
         "generation_top_k": settings.RETRIEVAL_TOP_K,
         "context": {"min_similarity": settings.CONTEXT_MIN_SIMILARITY, "max_similarity_drop": settings.CONTEXT_MAX_SIMILARITY_DROP, "max_chars": settings.RAG_MAX_CONTEXT_CHARS},
         "generation_code_sha256": fingerprint(Path("app/graph/nodes.py").read_text(encoding="utf-8")),
         "memory": Path("/proc/meminfo").read_text().splitlines()[0] if Path("/proc/meminfo").exists() else "host metadata required"})
    if args.dataset:
        records = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if len(records) != 50:
            raise ValueError("Expected 50 candidate questions.")
        for r in records:
            if r["document_id"] not in APPROVED.values():
                raise ValueError("Unapproved candidate document.")
            words = set(r["question"].lower().split())
            matches = sorted((c for c in value["chunks"] if c["document_id"] == r["document_id"]),
                             key=lambda c: (-len(words.intersection(c["content"].lower().split())), c["id"]))[:3]
            r["candidate_passages"] = [{"passage_id": c["id"], "document_id": c["document_id"], "page_number": c["page_number"], "excerpt": c["content"]} for c in matches]
            r["corpus_sha256"] = value["corpus_sha256"]
        (out / "questions.candidates.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    report(out)


async def run(args):
    out = Path(args.output)
    frozen = json.loads((out / "corpus.json").read_text(encoding="utf-8"))
    expected = frozen.pop("corpus_sha256")
    if fingerprint(frozen) != expected or fingerprint(snapshot()) != expected:
        raise ValueError("Frozen corpus has changed; refusing evaluation.")
    records = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    validate_judgments(records, frozen)
    if any(r.get("corpus_sha256") != expected for r in records):
        raise ValueError("Every reviewed record must identify this frozen corpus hash.")
    examples = load_benchmark_dataset(args.dataset, split=args.split)
    if not examples:
        raise ValueError("No reviewed examples for the requested split.")
    # Persist the exact reviewed inputs used by this split, never rewrite them.
    dataset_target = out / f"questions.reviewed.{args.split}.jsonl"
    if dataset_target.exists():
        raise ValueError("This split already has reviewed inputs; use a new run directory.")
    dataset_target.write_bytes(Path(args.dataset).read_bytes())
    retrieve = scoped_retriever(frozen, retrieval_service.retrieve_chunks)
    benchmark = RetrievalBenchmark(embed=embedding_service.get_embedding, retrieve=retrieve, top_k=10)
    reports = {}
    for mode in ("dense", "lexical", "hybrid"):
        reports[mode] = await benchmark.run(examples, mode=mode, dense_threshold=settings.RELEVANCE_THRESHOLD,
                                             lexical_threshold=settings.LEXICAL_RELEVANCE_THRESHOLD)
    if fingerprint(snapshot()) != expected:
        raise ValueError("Corpus changed during evaluation; results rejected.")
    result = {"corpus_sha256": expected, "dataset_sha256": __import__("hashlib").sha256(Path(args.dataset).read_bytes()).hexdigest(),
              "split": args.split, "reports": reports, "conditions": {"top_k": 10, "mrr_cutoff": 10,
              "latency": "SQL retrieval only; embedding latency recorded separately; single sequential pass; cold/warm order not controlled",
              "models": {"embedding": settings.EMBEDDING_MODEL, "generation": settings.LLM_MODEL}}}
    target = out / f"retrieval.{args.split}.json"
    if target.exists():
        raise ValueError("Results already exist; use a fresh run directory to preserve evidence.")
    save(target, result)
    export_csv_report(result, out / f"retrieval.{args.split}.csv")
    if args.answers:
        await answers(examples, retrieve, out, args.split)
        if fingerprint(snapshot()) != expected:
            save(out / "INVALIDATED.json", {"reason": "Corpus changed during answer generation; do not publish these results."})
            raise ValueError("Corpus changed during answer generation.")
    report(out)


async def answers(examples, retrieve, out, split):
    """Production generation/context/gate with strict research retrieval scope.

    Semantic quality stays pending human assessment of these exact predictions.
    Reference-answer claim labels are deliberately not applied to generated claims.
    """
    from app.graph.nodes import generate_node, grade_relevance_node, refuse_node, cite_node
    rows = []
    for e in examples:
        started = time.perf_counter()
        try:
            embedding = await embedding_service.get_embedding(e.question)
            chunks = [asdict(c) for c in await retrieve(embedding, query_text=e.question, mode="hybrid", top_k=settings.RETRIEVAL_TOP_K,
                      candidate_multiplier=settings.RETRIEVAL_CANDIDATE_MULTIPLIER, rrf_k=settings.RETRIEVAL_RRF_K)]
            state = {"question": e.question, "retrieved_chunks": chunks, "mode": "query"}
            state.update(await grade_relevance_node(state))
            state.update(await generate_node(state) if state["is_relevant"] else await refuse_node(state))
            state.update(await cite_node(state))
            rows.append({"id": e.id, "answer": state["answer"], "answer_sha256": fingerprint(state["answer"]), "is_refused": state["is_refused"], "expected_answerable": e.answerable,
                         "citations": state["citations"], "context_chunks": state.get("context_chunks", []),
                         "structural_audit": state["faithfulness_audit"], "response_latency_ms": (time.perf_counter() - started) * 1000,
                         "human_quality_review": {"status": "pending", "correctness": None, "faithfulness": None, "citation_support": None, "hallucination": None}})
        except Exception as exc:
            rows.append({"id": e.id, "failure_type": type(exc).__name__})
        # Checkpoint expensive predictions after every question.
        save(out / f"answers.{split}.json", {"predictions": rows, "semantic_metrics_status": "pending human review of exact generated claims"})
    latencies = [r["response_latency_ms"] for r in rows if "response_latency_ms" in r]
    save(out / f"answer_latency.{split}.json", {"successful_answers": len(latencies), "failures": len(rows) - len(latencies),
         "p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95)})


def score_answers(args):
    """Score explicit human reviews of these exact answers, never model labels."""
    out = Path(args.output)
    predictions = json.loads((out / f"answers.{args.split}.json").read_text(encoding="utf-8"))["predictions"]
    reviews = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    successful = [p for p in predictions if "answer" in p]
    if len(reviews) != len(successful) or len({r["id"] for r in reviews}) != len(reviews):
        raise ValueError("Exactly one human review is required for each successful prediction.")
    by_id = {r["id"]: r for r in reviews}
    correct = supported = contradicted = unsupported = citations = supported_citations = hallucinated = appropriate = 0
    for p in successful:
        r = by_id.get(p["id"], {})
        if r.get("provenance") != "human" or not r.get("reviewer_id") or not r.get("rationale") or r.get("answer_sha256") != p["answer_sha256"]:
            raise ValueError("Human review must identify the exact generated answer hash.")
        if not isinstance(r.get("correct"), bool) or not isinstance(r.get("hallucination_present"), bool):
            raise ValueError("Correctness and hallucination require explicit boolean human judgments.")
        claims = r.get("claims")
        verdicts = r.get("citation_reviews")
        if not isinstance(claims, list) or not isinstance(verdicts, list) or (not p["is_refused"] and not claims):
            raise ValueError("Review all factual claims and all inline citations; abstentions may have no claims.")
        contexts = {c["id"] for c in p["context_chunks"]}
        for claim in claims:
            if not claim.get("text") or claim.get("label") not in {"supported", "contradicted", "unsupported"}:
                raise ValueError("Invalid human claim judgment.")
            if not set(claim.get("passage_ids", [])).issubset(contexts):
                raise ValueError("Human judgments cannot cite passages outside the supplied included corpus.")
            if claim["label"] == "supported" and (not claim.get("passage_ids") or not set(claim["passage_ids"]).issubset(contexts)):
                raise ValueError("Supported claims require supplied in-scope passages.")
            supported += claim["label"] == "supported"
            contradicted += claim["label"] == "contradicted"
            unsupported += claim["label"] == "unsupported"
        expected_refs = set(p["structural_audit"]["valid_source_references"] + p["structural_audit"]["invalid_source_references"])
        if len(verdicts) != len(expected_refs) or {v.get("source_index") for v in verdicts} != expected_refs:
            raise ValueError("Human citation reviews must cover every unique inline source reference.")
        for v in verdicts:
            if not isinstance(v.get("supports_claim"), bool):
                raise ValueError("Citation support requires a boolean human judgment.")
            if v["supports_claim"] and v["source_index"] not in p["structural_audit"]["valid_source_references"]:
                raise ValueError("An invalid source reference cannot support a claim.")
            supported_citations += v["supports_claim"]
        citations += len(verdicts)
        correct += r["correct"]
        hallucinated += r["hallucination_present"]
        appropriate += p["is_refused"] == (not p["expected_answerable"])
    count = len(successful)
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    save(out / f"answer_quality.{args.split}.json", {"review_provenance": "human", "review_sha256": __import__("hashlib").sha256(Path(args.dataset).read_bytes()).hexdigest(),
        "reviewed_answers": count, "generation_failures": len(predictions)-count, "correctness": ratio(correct,count),
        "faithfulness": ratio(supported,supported+contradicted+unsupported), "contradicted_claims": contradicted,
        "unsupported_claims": unsupported, "citation_support_precision": ratio(supported_citations,citations),
        "hallucination_frequency": ratio(hallucinated,count), "appropriate_abstention": ratio(appropriate,count)})
    report(out)


async def smoke(args):
    """Live read-only retrieval and dependency checks, no relevance labels."""
    import httpx
    out = Path(args.output)
    frozen = json.loads((out / "corpus.json").read_text(encoding="utf-8"))
    expected = frozen.pop("corpus_sha256")
    if fingerprint(frozen) != expected or fingerprint(snapshot()) != expected:
        raise ValueError("Corpus drift before smoke check.")
    rows = []
    retrieve = scoped_retriever(frozen, retrieval_service.retrieve_chunks)
    for d in frozen["documents"]:
        chunk = next(c for c in frozen["chunks"] if c["document_id"] == d["id"])
        query = " ".join(chunk["content"].split()[:12])
        embedding = await embedding_service.get_embedding(query)
        for mode in ("dense", "lexical", "hybrid"):
            start = time.perf_counter()
            found = await retrieve(embedding if mode != "lexical" else [], query_text=query, top_k=10, mode=mode)
            if mode != "lexical" and not found:
                raise ValueError("Dense/hybrid smoke returned no included chunks.")
            rows.append({"document_probe": d["id"], "mode": mode, "query": query,
                         "retrieved": [asdict(c) for c in found], "latency_ms": (time.perf_counter()-start)*1000})
    async with httpx.AsyncClient(timeout=30) as client:
        tags = (await client.get(settings.OLLAMA_BASE_URL.rstrip("/") + "/api/tags"))
        tags.raise_for_status()
        save(out / "ollama_models.json", tags.json())
        checks = {}
        for path in ("health/live", "health/ready", "documents/"):
            response = await client.get("http://127.0.0.1:8000" + settings.API_V1_STR + "/" + path)
            checks[path] = response.status_code
        if checks != {"health/live": 200, "health/ready": 200, "documents/": 401}:
            raise ValueError(f"Unexpected API smoke status codes: {checks}")
    save(out / "software_smoke.json", {"kind": "engineering smoke; no accuracy evidence", "api_status": checks, "retrieval_probes": rows})


def report(out):
    out = Path(out)
    corpus = json.loads((out / "corpus.json").read_text(encoding="utf-8"))
    lines = ["# LearnMateAI: Retrieval Evaluation on Nine Class 10 Science Chapters", "",
        "## Abstract", "", "This bounded study covers chapters 1, 2, 3, 7, 9, 10, 11, 12, and 13. Chapters 4, 5, 6, and 8 are excluded because of unresolved ingestion failures. This is not a complete 13-chapter evaluation.", "",
        "## I. Corpus and protocol", "", f"Corpus SHA-256: `{corpus['corpus_sha256']}`. Nine allowlisted documents, 643 chunks, 1024-dimensional embeddings. Both document and frozen chunk IDs constrain SQL candidates before ranking. No excluded document is queried or retried.", "",
        "| Chapter | Document ID | Chunks | Dimension |", "| --- | --- | ---: | ---: |"]
    lines += [f"| {d['chapter_number']} | {d['id']} | {d['chunks']} | 1024 |" for d in corpus["documents"]]
    lines += ["", "## II. Retrieval results", "", "Gold passages require human review. Reference answers and evidence spans must come only from the frozen included corpus. Dev/test splits are fixed before evaluation; this runner performs no threshold tuning."]
    found = False
    for path in sorted(out.glob("retrieval.*.json")):
        found = True
        data = json.loads(path.read_text(encoding="utf-8"))
        lines += ["", f"Split: {data['split']}; dataset SHA-256: `{data['dataset_sha256']}`.", "",
                  "| Mode | n | P@5 | R@5 | MRR@10 | nDCG@10 | p50 ms | p95 ms |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for mode, r in data["reports"].items():
            a = r["aggregate"]
            lines.append(f"| {mode} | {a['examples']} | {a['precision_at_5']:.4f} | {a['recall_at_5']:.4f} | {a['mrr']:.4f} | {a['ndcg_at_10']:.4f} | {a['retrieval_latency_p50_ms']:.3f} | {a['retrieval_latency_p95_ms']:.3f} |")
    if not found:
        lines += ["", "No reviewed benchmark was executed; retrieval metrics are unavailable."]
    lines += ["", "## III. Answer evaluation", "", "Generated answers and source contexts are saved for human assessment of correctness, claim support, contradictions, hallucinations, and citation entailment. Structural source-reference checks alone cannot establish factual correctness. Semantic quality metrics remain unavailable until those exact predictions are reviewed.", "",
              "## IV. Software verification", "", "Keep software test logs and API/database smoke results separate from research accuracy. See host execution logs; this report does not infer live test success.", "",
              "## V. Threats to validity", "", "Excluding four chapters introduces selection bias toward successfully parsed material and limits curricular coverage. Fifty questions yield limited statistical power. Incomplete relevance judgments can underestimate recall. Single-pass timings depend on caching, query order, hardware and model load. Lexical latency excludes embeddings; embedding/total latency are separate traces. No claim extends to the full textbook or educational learning gains."]
    for quality in sorted(out.glob("answer_quality.*.json")):
        values = json.loads(quality.read_text(encoding="utf-8"))
        lines += ["", f"### Human-reviewed answer results: {quality.name}", "", "| Measurement | Value |", "| --- | ---: |"]
        lines += [f"| {key} | {values[key]} |" for key in ("reviewed_answers", "generation_failures", "correctness", "faithfulness", "contradicted_claims", "unsupported_claims", "citation_support_precision", "hallucination_frequency", "appropriate_abstention")]
    for timing in sorted(out.glob("answer_latency.*.json")):
        lines += ["", f"Response latency ({timing.name}): `{timing.read_text(encoding='utf-8').strip()}`"]
    (out / "IEEE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "report", "smoke", "score-answers"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--answers", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args)
    elif args.command == "run":
        asyncio.run(run(args))
    elif args.command == "smoke":
        asyncio.run(smoke(args))
    elif args.command == "score-answers":
        score_answers(args)
    else:
        report(args.output)


if __name__ == "__main__":
    main()
