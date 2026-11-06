import asyncio
import unittest

from app.evaluation.faithfulness import audit_answer, faithfulness_metrics
from app.evaluation.retrieval_benchmark import BenchmarkExample, RetrievalBenchmark
from app.graph.nodes import cite_node
from app.services.retrieval_service import RetrievedChunk


def _source(index=1, content="Water boils at 100 C at sea level."):
    return {
        "id": f"chunk-{index}", "document_id": "document-1", "document_title": "Science",
        "page_number": index, "chunk_index": index, "content": content,
    }


class FaithfulnessTests(unittest.TestCase):
    def test_human_verified_claim_with_real_source_is_supported(self):
        report = audit_answer(
            "Water boils at 100 C at sea level. [Source 1]",
            [_source()],
            human_labels={"water boils at 100 c at sea level.": "supported"},
        )
        self.assertEqual(report["valid_source_references"], [1])
        self.assertEqual(report["claims"][0]["status"], "supported")

    def test_nonexistent_source_is_detected_and_claim_is_insufficient(self):
        report = audit_answer("Water boils at 100 C. [Source 9]", [_source()])
        self.assertEqual(report["invalid_source_references"], [9])
        self.assertEqual(report["claims"][0]["status"], "insufficiently_evidenced")

    def test_unverified_string_overlap_never_becomes_support(self):
        report = audit_answer("Water boils at 100 C. [Source 1]", [_source()])
        self.assertEqual(report["claims"][0]["status"], "insufficiently_evidenced")

    def test_human_verified_contradiction_is_retained(self):
        report = audit_answer(
            "Water boils at 90 C. [Source 1]", [_source()],
            human_labels={"water boils at 90 c.": "contradicted"},
        )
        self.assertEqual(report["claims"][0]["status"], "contradicted")

    def test_empty_context_marks_reference_invalid_and_abstention_appropriate(self):
        report = audit_answer("I cannot answer because the textbook context is insufficient. [Source 1]", [])
        metrics = faithfulness_metrics([report], expected_answerable=[False])
        self.assertEqual(report["invalid_source_references"], [1])
        self.assertTrue(report["is_abstention"])
        self.assertEqual(metrics["appropriate_abstention_rate"], 1.0)

    def test_citation_node_reaudits_inline_references_without_changing_citations(self):
        result = asyncio.run(cite_node({"answer": "Claim [Source 4]", "context_chunks": [_source()]}))
        self.assertEqual(result["citations"][0]["source_index"], 1)
        self.assertEqual(result["faithfulness_audit"]["invalid_source_references"], [4])

    def test_benchmark_can_persist_faithfulness_trace_when_generator_is_supplied(self):
        async def embed(_question):
            return [0.1]

        async def retrieve(_embedding, **_kwargs):
            return [RetrievedChunk("chunk-1", "document-1", "Science", "Water boils at 100 C.", 1, None, 0, 0.9)]

        async def generate(_question, _chunks):
            return "Water boils at 100 C. [Source 1]"

        report = asyncio.run(RetrievalBenchmark(embed=embed, retrieve=retrieve).run(
            [BenchmarkExample("When does water boil?", ("chunk-1",), True, {})],
            mode="hybrid", dense_threshold=0.55, lexical_threshold=0.08, answer_generator=generate,
        ))
        self.assertIn("faithfulness", report["predictions"][0])
        self.assertEqual(report["aggregate"]["faithfulness"]["invalid_citations"], 0)
