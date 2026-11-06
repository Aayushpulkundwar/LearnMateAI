import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation.retrieval_benchmark import (
    BenchmarkExample,
    RetrievalBenchmark,
    load_benchmark_dataset,
    select_dev_thresholds,
)
from app.services.retrieval_service import RetrievedChunk


def _chunk(chunk_id, *, dense=0.0, lexical=0.0):
    return RetrievedChunk(chunk_id, "doc", "Book", "text", 1, "One", 0, dense, lexical)


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_loads_jsonl_aliases_and_split_without_relaxing_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text(
                json.dumps({"id": "dev-1", "question": "Q", "gold_chunk_ids": ["c1"], "expected_relevant": True, "split": "dev", "filters": {"chapter": "One"}}) + "\n" +
                json.dumps({"id": "test-1", "question": "No", "gold_passage_ids": [], "answerable": False, "split": "test"}) + "\n",
                encoding="utf-8",
            )
            examples = load_benchmark_dataset(path, split="dev")
        self.assertEqual(examples, [BenchmarkExample("Q", ("c1",), True, {"chapter": "One"}, "dev", "dev-1")])

    def test_reports_retrieval_metrics_gates_and_per_query_trace(self):
        calls = []

        async def embed(question):
            return [0.1]

        async def retrieve(embedding, **kwargs):
            calls.append(kwargs)
            if kwargs["query_text"] == "supported":
                return [_chunk("gold", dense=0.8, lexical=0.2), _chunk("other", dense=0.7)]
            return [_chunk("other", dense=0.2, lexical=0.0)]

        result = asyncio.run(RetrievalBenchmark(embed=embed, retrieve=retrieve, top_k=5).run(
            [
                BenchmarkExample("supported", ("gold",), True, {"chapter": "One"}, id="1"),
                BenchmarkExample("unsupported", (), False, {}, id="2"),
            ], mode="hybrid", dense_threshold=0.55, lexical_threshold=0.08,
        ))
        aggregate = result["aggregate"]
        self.assertEqual(aggregate["precision_at_5"], 0.2)
        self.assertEqual(aggregate["recall_at_5"], 1.0)
        self.assertEqual(aggregate["mrr"], 1.0)
        self.assertEqual(aggregate["ndcg_at_10"], 1.0)
        self.assertEqual(aggregate["false_refusal_rate"], 0.0)
        self.assertEqual(aggregate["unsupported_query_acceptance_rate"], 0.0)
        self.assertEqual(calls[0]["chapter"], "One")
        self.assertEqual(calls[0]["mode"], "hybrid")
        self.assertIn("retrieval_latency_ms", result["predictions"][0])

    def test_calibration_selects_from_development_predictions_only(self):
        calibrated = select_dev_thresholds(
            [
                {"answerable": True, "max_dense_score": 0.7, "max_lexical_score": 0.0},
                {"answerable": False, "max_dense_score": 0.4, "max_lexical_score": 0.0},
            ], dense_candidates=[0.4, 0.7], lexical_candidates=[1.0],
        )
        self.assertEqual(calibrated["dense_threshold"], 0.7)
        self.assertEqual(calibrated["f1"], 1.0)
