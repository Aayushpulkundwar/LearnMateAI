"""Run a retrieval-free Ollama baseline on the predeclared development subset."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EXPECTED_CORPUS = "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8"
EXPECTED_MODEL = "llama3:8b"
EXPECTED_DIGEST = "365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1"
SYSTEM = "You are an educational assistant. Answer the student's question clearly and concisely. Do not cite or imply access to external sources. If uncertain, say so."


def build_prompt(question: str) -> str:
    """Construct the retrieval-free user prompt from question text only."""
    return f"Student question: {question}\n\nAnswer:"


def validate_generation_response(payload: dict[str, Any]) -> str:
    answer = payload.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Ollama returned an empty response")
    return answer.strip()


def read_questions(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not rows or any(row.get("corpus_sha256") != EXPECTED_CORPUS for row in rows):
        raise ValueError("Question dataset is empty or does not match the frozen fingerprint")
    dev = [row for row in rows if row.get("split") == "dev"]
    if len(dev) < 10:
        raise ValueError("At least 10 development questions are required")
    return dev[:10]


def get_json(url: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run(root: Path = ROOT, base_url: str = "http://127.0.0.1:11434") -> Path:
    manifest = json.loads((root / "experiment_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("frozen_run_id") != "nine_science_03" or manifest.get("corpus_sha256") != EXPECTED_CORPUS:
        raise ValueError("Frozen run manifest mismatch")
    config = json.loads((root / "system_configuration.json").read_text(encoding="utf-8"))
    expected = config.get("generation_model", {}).get("value", {}).get("digest")
    if expected and expected != EXPECTED_DIGEST:
        raise ValueError("Frozen model digest differs from expected model identity")
    tags = get_json(base_url.rstrip("/") + "/api/tags")
    model = next((m for m in tags.get("models", []) if m.get("name") == EXPECTED_MODEL), None)
    if not model:
        raise RuntimeError(f"Required model {EXPECTED_MODEL} is not installed; downloads are disabled")
    digest = model.get("digest")
    if digest != EXPECTED_DIGEST:
        raise RuntimeError("Installed model digest differs from the frozen identity; refusing generation")
    questions_path = root / "datasets" / "questions.jsonl"
    questions = read_questions(questions_path)
    output = root / "generation" / "no_retrieval.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    selected_ids = [q["id"] for q in questions]
    records: list[dict[str, Any]] = []
    for q in questions:
        prompt = build_prompt(q["question"])
        started = time.perf_counter()
        record: dict[str, Any] = {
            "question_id": q["id"], "split": q["split"], "condition": "no_retrieval",
            "question": q["question"], "prompt": prompt, "system_prompt": SYSTEM,
            "model": EXPECTED_MODEL, "model_digest": digest,
            "settings": {"temperature": 0.2, "stream": False, "context_length": 8192,
                         "max_response_tokens": None, "seed": None,
                         "settings_source": "frozen manifest and backend config; context from model tag; generation API exposes temperature only"},
            "retrieved_evidence_included": False, "answer": None, "citations": [], "latency_seconds": None,
            "status": "error", "error": None, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            result = post_json(base_url.rstrip("/") + "/api/generate", {
                "model": EXPECTED_MODEL, "prompt": prompt, "system": SYSTEM, "stream": False,
                "options": {"temperature": 0.2},
            })
            record["answer"] = validate_generation_response(result)
            record["status"] = "success"
            record["ollama_total_duration_ns"] = result.get("total_duration")
            record["ollama_load_duration_ns"] = result.get("load_duration")
        except Exception as exc:  # record failure, never synthesize a response
            record["error"] = type(exc).__name__
        record["latency_seconds"] = time.perf_counter() - started
        records.append(record)
    payload = {
        "frozen_run_id": "nine_science_03", "corpus_sha256": EXPECTED_CORPUS,
        "source_dataset_sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
        "selection_rule": "first ten development records in the immutable selected-dataset order; no held-out records",
        "selected_question_ids": selected_ids, "model": EXPECTED_MODEL, "model_digest": digest,
        "created_utc": datetime.now(timezone.utc).isoformat(), "records": records,
    }
    # Exclusive create ensures prior outputs are never silently replaced.
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    path = run(args.root, args.ollama_url)
    data = json.loads(path.read_text(encoding="utf-8"))
    succeeded = sum(r["status"] == "success" for r in data["records"])
    print(f"No-retrieval baseline: {succeeded}/{len(data['records'])} successful; output={path}")
    return 0 if succeeded == len(data["records"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
