"""Write a new, append-only Part 2 execution-status snapshot (no DB access)."""
import csv
import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    spec = importlib.util.spec_from_file_location("eval_retrieval", ROOT / "eval_retrieval.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    validation = module.validate_run_files(ROOT)
    annotation_rows = {}
    for number in (1, 2):
        path = ROOT / "annotations" / f"reviewer_{number}.csv"
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as f: rows = list(csv.DictReader(f))
            annotation_rows[f"reviewer_{number}"] = {"candidate_rows": len(rows),
                "explicit_relevance_labels": sum(bool(r.get("relevance", "").strip()) for r in rows),
                "reviewer_ids": sorted({r.get("reviewer_id", "").strip() for r in rows if r.get("reviewer_id", "").strip()})}
    result_dir = ROOT / "results"
    files = {}
    for relative in ("runs/dense.json", "runs/fts.json", "runs/hybrid.json", "annotations/reviewer_1.csv", "annotations/reviewer_2.csv",
                     "annotations/pool_origin_mapping.json", "generation/no_retrieval.json", "generation/run_manifest.json",
                     "results/ieee_research_results.md"):
        files[relative] = sha(ROOT / relative)
    base = json.loads((ROOT / "generation" / "no_retrieval.json").read_text(encoding="utf-8"))
    test_log = result_dir / "part2_unit_tests_12.log"
    test_text = test_log.read_text(encoding="utf-8") if test_log.is_file() else ""
    test_count = int(test_text.split("Ran ", 1)[1].split(" tests", 1)[0]) if "Ran " in test_text else None
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parents[2], capture_output=True, text=True)
    status = {"captured_utc": datetime.now(timezone.utc).isoformat(), "git_commit": git.stdout.strip() if git.returncode == 0 else None,
        "frozen_run_id": validation["frozen_run_id"], "corpus_sha256": validation["corpus_sha256"],
        "dataset_sha256": validation["dataset_sha256"], "retrieval_trace_validation": validation,
        "human_relevance_review": {"rows": annotation_rows, "gold_json_present": (ROOT / "gold.json").exists(),
                                   "metrics_status": "blocked pending complete independent reviews and explicit adjudication"},
        "generation": {"no_retrieval": {"successes": sum(r.get("status") == "success" for r in base["records"]),
             "questions": len(base["records"]), "model": base["model"], "model_digest": base["model_digest"], "latency_seconds": json.loads((ROOT / "generation" / "run_manifest.json").read_text(encoding="utf-8"))["latency_seconds"]},
             "rag_json_present": (ROOT / "generation" / "rag.json").exists(), "answer_review_status": "not available until RAG generation and human review"},
        "software_tests": {"log": str(test_log.relative_to(ROOT)), "tests_run": test_count, "passed": test_count if "OK" in test_text else None,
                           "failed": 0 if "OK" in test_text else None},
        "artifact_sha256": files,
        "ieee_measurements": {"retrieval_metrics": "not produced", "generation_quality_metrics": "not produced", "figures": "withheld until validated measurements"}}
    out = result_dir / "part2_execution_status_02.json"
    with out.open("x", encoding="utf-8") as f: json.dump(status, f, indent=2); f.write("\n")
    print(out)


if __name__ == "__main__": main()
