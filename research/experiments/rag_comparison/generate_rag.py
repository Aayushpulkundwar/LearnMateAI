"""Run the existing authenticated LearnMateAI query API; credentials remain in memory."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FINGERPRINT = "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8"
APPROVED_DOCS = {"6b418b53-971c-4547-b4ac-e0eae9fdff92", "93116cc1-6a00-4968-9268-59db13424b09", "4a8d4852-5979-45ca-b5b2-44b994ec2385", "1360321a-7a0d-417a-a1d4-560a635693e1", "a92321fa-f136-4203-95e3-550530be58f7", "925e4a60-1e33-4394-a333-485a7682e584", "c9981302-fda6-45bc-ab4e-c142379f0035", "c71bbe0c-0206-4a2c-bb13-d6fa2802f9b4", "672dfbdf-af01-4c86-9321-f034f6d25aa9"}


def _request(opener: urllib.request.OpenerDirector, url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _get_json(url: str, timeout: int = 10) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode())


def build_query_payload(question: str, document_id: str) -> dict[str, Any]:
    if document_id not in APPROVED_DOCS:
        raise ValueError("Document is outside the frozen nine-chapter allowlist")
    return {"question": question, "document_id": document_id, "grade": "10", "subject": "Science", "explanation_depth": "standard"}


def run(root: Path = ROOT, base_url: str = "http://127.0.0.1:8000") -> Path:
    manifest = json.loads((root / "experiment_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("frozen_run_id") != "nine_science_03" or manifest.get("corpus_sha256") != FINGERPRINT:
        raise ValueError("Frozen run manifest mismatch")
    questions_path = root / "datasets" / "questions.jsonl"
    questions = [json.loads(s) for s in questions_path.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    questions = [q for q in questions if q.get("split") == "dev"][:10]
    if len(questions) != 10 or any(q.get("document_id") not in APPROVED_DOCS for q in questions):
        raise ValueError("The fixed ten-development-question set is incomplete or outside the frozen allowlist")
    out = root / "generation" / "rag.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    ready = _get_json(base_url.rstrip("/") + "/api/v1/health/ready")
    if ready.get("status") != "healthy":
        raise RuntimeError("LearnMateAI API dependencies are not healthy; no credentials or queries were submitted")
    identity = input("After verifying current_database/current_user, enter the exact approved staging identity (database|user): ").strip()
    if identity != "learnmate_db|tutor":
        raise RuntimeError("Database identity confirmation did not match the frozen approved staging identity")
    model_digest = input("After verifying the API's Ollama model digest, enter the frozen llama3:8b digest: ").strip()
    if model_digest != "365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1":
        raise RuntimeError("Model digest confirmation did not match frozen llama3:8b")
    email = input("LearnMateAI test-account email: ").strip()
    password = getpass.getpass("LearnMateAI password (not stored or displayed): ")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        _request(opener, base_url.rstrip("/") + "/api/v1/auth/login", {"email": email, "password": password}, timeout=30)
    except Exception as exc:
        raise RuntimeError(f"Authentication failed ({type(exc).__name__}); no query was issued") from None
    finally:
        password = ""
    # Validate the login set a session cookie without ever printing its name/value.
    if not list(jar): raise RuntimeError("Login succeeded without an authenticated session cookie")
    config = json.loads((root / "system_configuration.json").read_text(encoding="utf-8"))
    gen = config.get("generation_model", {}).get("value", {})
    records = []
    for q in questions:
        payload = build_query_payload(q["question"], q["document_id"])
        started = time.perf_counter()
        rec = {"question_id": q["id"], "split": q["split"], "condition": "rag", "question": q["question"],
               "request_prompt": payload, "server_prompt": "Production LangGraph prompt; exact rendered prompt is not exposed by the authenticated API.",
               "prompt_source": "backend/app/graph/nodes.py:generate_node", "model": gen.get("tag"), "model_digest": gen.get("digest"),
               "settings": {"temperature": 0.2, "context_length": 8192, "max_response_tokens": None, "seed": None,
                            "note": "Values from frozen configuration; per-request API does not expose rendered generation options."},
               "answer": None, "citations": [], "latency_seconds": None, "status": "error", "error": None}
        try:
            result = _request(opener, base_url.rstrip("/") + "/api/v1/query/", payload)
            cites = result.get("citations", [])
            if any(str(c.get("document_id")) not in APPROVED_DOCS for c in cites):
                raise ValueError("citation outside frozen chapter allowlist")
            answer = result.get("answer")
            if not isinstance(answer, str) or not answer.strip(): raise ValueError("empty answer")
            rec.update(answer=answer, citations=cites, is_refused=result.get("is_refused", False), status="success")
        except urllib.error.HTTPError as exc:
            rec["error"] = f"HTTP_{exc.code}"
        except Exception as exc:
            rec["error"] = type(exc).__name__
        rec["latency_seconds"] = time.perf_counter() - started
        records.append(rec)
    output = {"frozen_run_id": "nine_science_03", "corpus_sha256": FINGERPRINT,
              "source_dataset_sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
              "selection_rule": "first ten development records in immutable selected-dataset order",
              "selected_question_ids": [q["id"] for q in questions], "model": gen.get("tag"), "model_digest": model_digest,
              "model_digest_confirmed_by_operator": True, "database_identity_confirmed_by_operator": identity,
              "created_utc": datetime.now(timezone.utc).isoformat(), "records": records}
    with out.open("x", encoding="utf-8") as f: json.dump(output, f, indent=2, ensure_ascii=False); f.write("\n")
    return out


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, default=ROOT); p.add_argument("--api", default="http://127.0.0.1:8000"); a = p.parse_args()
    path = run(a.root, a.api); result = json.loads(path.read_text(encoding="utf-8")); count = sum(r["status"] == "success" for r in result["records"])
    print(f"LearnMateAI RAG: {count}/{len(result['records'])} successful; output={path}")
    return 0 if count == len(result["records"]) else 2


if __name__ == "__main__": raise SystemExit(main())
