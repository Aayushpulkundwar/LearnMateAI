"""Capture metadata for the already executed retrieval-free Ollama run."""
import hashlib
import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    generation = ROOT / "generation" / "no_retrieval.json"
    questions = ROOT / "datasets" / "questions.jsonl"
    source = ROOT / "generate_no_retrieval.py"
    data = json.loads(generation.read_text(encoding="utf-8"))
    latencies = [float(x["latency_seconds"]) for x in data["records"]]
    out = ROOT / "generation" / "run_manifest.json"
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "frozen_run_id": data["frozen_run_id"],
        "corpus_sha256": data["corpus_sha256"], "selection_rule": data["selection_rule"],
        "selected_question_ids": data["selected_question_ids"], "source_dataset_sha256": digest(questions),
        "generation_output_sha256": digest(generation), "runner_sha256": digest(source),
        "model": data["model"], "model_digest": data["model_digest"], "temperature": 0.2,
        "condition": "retrieval-free Ollama baseline", "successes": sum(x["status"] == "success" for x in data["records"]),
        "total_questions": len(data["records"]), "latency_seconds": {"mean": statistics.fmean(latencies), "median": statistics.median(latencies),
            "p95_linear_interpolation": sorted(latencies)[int((len(latencies)-1)*.95)] + (sorted(latencies)[min(int((len(latencies)-1)*.95)+1, len(latencies)-1)]-sorted(latencies)[int((len(latencies)-1)*.95)]) * (((len(latencies)-1)*.95) % 1)},
        "runtime": {"python": platform.python_version(), "platform": platform.platform(), "cpu_count": __import__("os").cpu_count()},
        "limitations": ["Exact Ollama hardware utilization and prompt token count not recorded", "No RAG condition or human answer judgments in this execution"]}
    with out.open("x", encoding="utf-8") as f: json.dump(summary, f, indent=2); f.write("\n")
    print(out)
    return 0


if __name__ == "__main__": raise SystemExit(main())
