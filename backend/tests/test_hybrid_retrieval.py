import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.evaluation.metrics import evaluate_retrieval_relevance
from app.graph.nodes import grade_relevance_node
from app.services.context_selection import select_context_chunks
from app.services.retrieval_service import reciprocal_rank_fusion


def _row(chunk_id, score, *, content="text"):
    chunk = SimpleNamespace(
        id=chunk_id, document_id="document-1", content=content,
        page_number=3, chapter="Chapter 1", chunk_index=1,
    )
    return chunk, SimpleNamespace(title="Textbook"), score


class HybridRetrievalTests(unittest.TestCase):
    def test_rrf_promotes_candidate_returned_by_both_retrievers(self):
        fused = reciprocal_rank_fusion(
            [_row("vector-only", 0.91), _row("both", 0.82)],
            [_row("both", 0.42), _row("lexical-only", 0.31)],
        )
        self.assertEqual([chunk.id for chunk in fused], ["both", "vector-only", "lexical-only"])
        self.assertEqual(fused[0].vector_rank, 2)
        self.assertEqual(fused[0].lexical_rank, 1)
        self.assertGreater(fused[0].rrf_score, fused[1].rrf_score)

    def test_rrf_retains_source_specific_scores_for_auditable_citations(self):
        fused = reciprocal_rank_fusion([_row("chunk", 0.73)], [_row("chunk", 0.25)])
        self.assertEqual(fused[0].similarity_score, 0.73)
        self.assertEqual(fused[0].lexical_score, 0.25)

    def test_lexical_evidence_can_pass_the_shared_relevance_gate(self):
        relevant, dense, lexical = evaluate_retrieval_relevance(
            [{"similarity_score": 0.12, "lexical_score": 0.20}],
            dense_threshold=0.55, lexical_threshold=0.08,
        )
        self.assertTrue(relevant)
        self.assertEqual((dense, lexical), (0.12, 0.20))

    def test_unrelated_low_signal_evidence_is_refused(self):
        with patch.object(settings, "RELEVANCE_THRESHOLD", 0.55), patch.object(settings, "LEXICAL_RELEVANCE_THRESHOLD", 0.08):
            result = asyncio.run(grade_relevance_node({"retrieved_chunks": [{"similarity_score": 0.30, "lexical_score": 0.01}]}))
        self.assertFalse(result["is_relevant"])
        self.assertEqual(result["max_lexical_score"], 0.01)

    def test_lexical_only_supporting_context_is_retained(self):
        top = {"id": "a", "similarity_score": 0.70}
        lexical = {"id": "b", "similarity_score": 0.10, "lexical_rank": 1, "lexical_score": 0.20}
        self.assertEqual(
            select_context_chunks([top, lexical], minimum_similarity=0.50, maximum_similarity_drop=0.06),
            [top, lexical],
        )
