import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation.review_dataset import (
    adjudicate_claim, append_review, export_csv_report, load_review_dataset,
    reviewer_agreement, validate_review_dataset,
)


def _record(split="dev", question="What is a procedure?"):
    return {
        "schema_version": "1.0", "id": "q-1", "split": split, "question": question,
        "document_id": "doc-1", "chapter_id": "chapter-1", "topic_id": "topic-1",
        "answerable": True, "gold_passage_ids": ["chunk-1"], "reference_answer": "A procedure is reusable SQL.",
        "evidence_spans": [{"passage_id": "chunk-1", "start_char": 0, "end_char": 12}],
        "claims": [{"id": "claim-1", "text": "A procedure is reusable SQL.", "reviews": [], "machine_suggestions": [{"label": "supported", "provenance": "machine"}]}],
    }


class ReviewDatasetTests(unittest.TestCase):
    def test_validates_review_schema_and_detects_cross_split_question_leakage(self):
        first, second = _record(), _record("test")
        second["id"] = "q-2"
        errors = validate_review_dataset([first, second])
        self.assertTrue(any("appears across splits" in error for error in errors))

    def test_review_disagreement_and_human_adjudication_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.jsonl"
            path.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
            append_review(path, record_id="q-1", claim_id="claim-1", reviewer_id="r1", label="supported", rationale="Direct text")
            append_review(path, record_id="q-1", claim_id="claim-1", reviewer_id="r2", label="contradicted", rationale="Wrong passage")
            agreement = reviewer_agreement(load_review_dataset(path))
            adjudicate_claim(path, record_id="q-1", claim_id="claim-1", adjudicator_id="lead", label="supported", rationale="Resolved")
            record = load_review_dataset(path)[0]
        self.assertEqual(agreement["disagreements"], 1)
        self.assertEqual(record["claims"][0]["adjudication"]["label"], "supported")
        self.assertEqual(record["claims"][0]["machine_suggestions"][0]["provenance"], "machine")

    def test_exports_existing_json_benchmark_report_as_csv(self):
        report = {"reports": {"hybrid": {"predictions": [{"id": "q-1", "question": "Q", "answerable": True, "accepted": True, "retrieved": [{"id": "chunk-1"}], "retrieval_latency_ms": 1.2}]}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            export_csv_report(report, path)
            content = path.read_text(encoding="utf-8")
        self.assertIn("retrieved_ids", content)
        self.assertIn("chunk-1", content)
