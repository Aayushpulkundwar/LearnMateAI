import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


metrics = load("eval_retrieval", "eval_retrieval.py")
baseline = load("generate_no_retrieval", "generate_no_retrieval.py")
review = load("answer_review", "answer_review.py")
rag_runner = load("generate_rag", "generate_rag.py")
ieee = load("generate_ieee_report", "generate_ieee_report.py")


class RetrievalMetricTests(unittest.TestCase):
    def make_fixture(self, root, answerable_ids=()):
        root.mkdir(parents=True, exist_ok=True)
        questions = [{"id": f"q{i}", "question": f"Question {i}", "split": "dev" if i < 18 else "test",
                      "chapter_number": 1, "document_id": "doc", "corpus_sha256": metrics.EXPECTED_CORPUS} for i in range(40)]
        (root / "datasets").mkdir()
        (root / "datasets" / "questions.jsonl").write_text("\n".join(json.dumps(x) for x in questions) + "\n")
        research_dir = root.parent.parent
        corpus_dir = research_dir / "results" / "nine_science_03"
        corpus_dir.mkdir(parents=True)
        docs = [{"id": f"doc{i}", "chapter_number": n} for i, n in enumerate((1,2,3,7,9,10,11,12,13))]
        chunks = [{"id": f"c{i}", "document_id": "doc0", "chapter": "chapter 1"} for i in range(643)]
        (corpus_dir / "corpus.json").write_text(json.dumps({"corpus_sha256": metrics.EXPECTED_CORPUS, "chunks": chunks}))
        (root / "frozen_corpus_report.json").write_text(json.dumps({"corpus_sha256": metrics.EXPECTED_CORPUS, "documents": docs}))
        return questions
    def test_precision_at_5(self): self.assertAlmostEqual(metrics.precision_at_5(["r", "x"], {"r"}), .2)
    def test_recall_at_5(self): self.assertAlmostEqual(metrics.recall_at_5(["r", "x"], {"r", "s"}), .5)
    def test_mrr_at_10(self): self.assertAlmostEqual(metrics.mrr_at_10(["x", "r"], {"r"}), .5)
    def test_ndcg_at_10(self): self.assertAlmostEqual(metrics.ndcg_at_10(["r", "x"], {"r"}), 1.0)
    def test_empty_ranking_scores_zero(self):
        self.assertEqual(metrics.precision_at_5([], {"r"}), 0)
        self.assertEqual(metrics.recall_at_5([], {"r"}), 0)
        self.assertEqual(metrics.mrr_at_10([], {"r"}), 0)
        self.assertEqual(metrics.ndcg_at_10([], {"r"}), 0)
    def test_unanswerable_has_no_ranking_metric(self):
        self.assertEqual(metrics.recall_at_5([], set()), 0)
    def test_aggregation_percentile(self): self.assertEqual(metrics.percentile([1, 2, 3, 4], .5), 2.5)
    def test_missing_gold_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "experiment_manifest.json").write_text(json.dumps({"frozen_run_id": "nine_science_03", "corpus_sha256": metrics.EXPECTED_CORPUS}))
            (root / "frozen_corpus_report.json").write_text(json.dumps({"corpus_sha256": metrics.EXPECTED_CORPUS}))
            with self.assertRaises(FileNotFoundError): metrics.evaluate(root)
    def test_fixture_evaluation_aggregates_empty_and_unanswerable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "research" / "experiments" / "rag_comparison"; (root / "runs").mkdir(parents=True)
            questions = self.make_fixture(root)
            (root / "experiment_manifest.json").write_text(json.dumps({"frozen_run_id": "nine_science_03", "corpus_sha256": metrics.EXPECTED_CORPUS}))
            gold = [{**questions[i], "answerable": i == 0, "relevance_judgments": {"c1": 1} if i == 0 else {},
                     "gold_provenance": "two independent human judgments; test fixture only"} for i in range(40)]
            (root / "gold.json").write_text(json.dumps(gold))
            (root / "gold_metadata.json").write_text(json.dumps({"corpus_sha256": metrics.EXPECTED_CORPUS, "questions": 40, "unjudged_passages_are_not_negative": True}))
            ds_hash = metrics.sha256(root / "datasets" / "questions.jsonl")
            for mode in metrics.MODES:
                (root / "runs" / f"{mode}.json").write_text(json.dumps({"run_id": "nine_science_03", "corpus_sha256": metrics.EXPECTED_CORPUS, "dataset_sha256": ds_hash, "mode": mode, "top_k": 10, "queries": [
                    {"question_id": f"q{i}", "mode": mode, "pre_gate_ranked": [], "latency_ms": 12 if i == 0 else 20, "status": "success"} for i in range(40)]}))
            result, rows = metrics.evaluate(root)
            self.assertEqual(result["modes"]["dense"]["answerable_scored"], 1)
            self.assertEqual(result["modes"]["dense"]["metrics"]["precision_at_5"]["mean"], 0)
            self.assertEqual(result["modes"]["dense"]["latency_ms"]["n"], 40)
            self.assertEqual(len(rows), 120)
    def test_unjudged_top10_is_excluded_not_negative(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "research" / "experiments" / "rag_comparison"; (root / "runs").mkdir(parents=True)
            questions = self.make_fixture(root)
            (root / "experiment_manifest.json").write_text(json.dumps({"frozen_run_id": "nine_science_03", "corpus_sha256": metrics.EXPECTED_CORPUS}))
            gold = [{**questions[i], "answerable": i == 0, "relevance_judgments": {"known": 1} if i == 0 else {},
                     "gold_provenance": "two independent human judgments; test fixture only"} for i in range(40)]
            (root / "gold.json").write_text(json.dumps(gold))
            (root / "gold_metadata.json").write_text(json.dumps({"corpus_sha256": metrics.EXPECTED_CORPUS, "questions": 40, "unjudged_passages_are_not_negative": True}))
            ds_hash = metrics.sha256(root / "datasets" / "questions.jsonl")
            for mode in metrics.MODES:
                (root / "runs" / f"{mode}.json").write_text(json.dumps({"run_id": "nine_science_03", "corpus_sha256": metrics.EXPECTED_CORPUS, "dataset_sha256": ds_hash, "mode": mode, "top_k": 10, "queries": [
                    {"question_id": f"q{i}", "mode": mode, "pre_gate_ranked": [{"rank":1,"chunk_id": "c1", "document_id":"doc0"}] if i == 0 else [], "latency_ms": 1, "status":"success"} for i in range(40)]}))
            result, rows = metrics.evaluate(root)
            self.assertEqual(result["modes"]["dense"]["incomplete_pooling_n"], 1)
            self.assertIsNone(rows[0]["precision_at_5"])
    def test_no_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); out = root / "results"; out.mkdir()
            (out / "retrieval_metrics.json").write_text("original")
            with self.assertRaises(FileExistsError): metrics.export({}, [], root)


class GenerationAndReviewTests(unittest.TestCase):
    def test_retrieval_free_prompt_contains_only_question(self):
        prompt = baseline.build_prompt("Why?")
        self.assertEqual(prompt, "Student question: Why?\n\nAnswer:")
        self.assertNotIn("chunk", prompt.lower()); self.assertNotIn("passage", prompt.lower())
    def test_generation_output_validation(self):
        self.assertEqual(baseline.validate_generation_response({"response": " ok "}), "ok")
        with self.assertRaises(ValueError): baseline.validate_generation_response({"response": " "})
    def test_rag_payload_is_document_scoped(self):
        doc = next(iter(rag_runner.APPROVED_DOCS))
        self.assertEqual(rag_runner.build_query_payload("Q", doc)["document_id"], doc)
        with self.assertRaises(ValueError): rag_runner.build_query_payload("Q", "excluded")
    def test_review_requires_all_scores(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review.csv"
            p.write_text(",".join(review.REQUIRED) + "\nq,Q,,,,,,,,,,,,,,,,\n", encoding="utf-8")
            with self.assertRaises(ValueError): review._read_review(p)
    def test_review_rejects_score_out_of_range(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review.csv"
            row = {key: "" for key in review.REQUIRED}; row.update(question_id="q", reviewer_id="R1", rationale="checked")
            for answer in ("a", "b"):
                for score in review.SCORES: row[f"score_{answer}_{score}"] = "2"
            row["score_a_correctness"] = "3"
            with p.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=review.REQUIRED); writer.writeheader(); writer.writerow(row)
            with self.assertRaises(ValueError): review._read_review(p)
    def test_review_valid_scores(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review.csv"
            row = {key: "" for key in review.REQUIRED}; row.update(question_id="q", reviewer_id="R1", rationale="reviewed")
            for answer in ("a", "b"):
                for score in review.SCORES: row[f"score_{answer}_{score}"] = "1"
            with p.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=review.REQUIRED); writer.writeheader(); writer.writerow(row)
            self.assertIn("q", review._read_review(p))
    def test_duplicate_question_ids_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "review.csv"; row = {key: "" for key in review.REQUIRED}
            row.update(question_id="q", reviewer_id="R1", rationale="checked")
            for answer in ("a", "b"):
                for score in review.SCORES: row[f"score_{answer}_{score}"] = "0"
            with p.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=review.REQUIRED); writer.writeheader(); writer.writerow(row); writer.writerow(row)
            with self.assertRaises(ValueError): review._read_review(p)
    def test_adjudication_export_requires_human_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); annotations = root / "annotations"; annotations.mkdir()
            (annotations / "answer_disagreements.csv").write_text("question_id,answer,metric,final_score,adjudicator_id,rationale,date\nq,A,correctness,,,,\n")
            with self.assertRaises(ValueError): review.adjudicate_and_export(root)
    def test_ieee_writer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "table.tex"; p.write_text("prior")
            with self.assertRaises(FileExistsError): ieee.write_new(p, "new")
    def test_explicit_ieee_refresh_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "report.md"; p.write_text("prior")
            with self.assertRaises(FileExistsError): ieee.write_artifact(p, "new")
            ieee.write_artifact(p, "new", refresh=True)
            self.assertEqual(p.read_text(), "new")
            self.assertEqual(p.with_name("report.pre_refresh.md").read_text(), "prior")


if __name__ == "__main__": unittest.main()
