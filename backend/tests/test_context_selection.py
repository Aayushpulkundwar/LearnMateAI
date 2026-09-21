import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.graph.nodes import generate_node
from app.services.context_selection import select_context_chunks


def _chunk(chunk_id, score, content="Evidence"):
    return {
        "id": chunk_id,
        "document_id": "doc-1",
        "document_title": "SQL PDF",
        "chapter": None,
        "page_number": 2,
        "chunk_index": int(chunk_id[-1]),
        "similarity_score": score,
        "content": content,
    }


class ContextSelectionTests(unittest.TestCase):
    def test_rank_one_is_retained_even_below_evidence_floor(self):
        chunks = [_chunk("chunk-1", 0.48), _chunk("chunk-2", 0.47)]
        selected = select_context_chunks(chunks, minimum_similarity=0.50, maximum_similarity_drop=0.06)
        self.assertEqual(selected, [chunks[0]])

    def test_combined_rule_keeps_useful_lower_ranked_insert_tree_evidence(self):
        top = _chunk("chunk-1", 0.567829)
        call = _chunk("chunk-2", 0.517456, "CALL InsertTree('Neem', 5, 'Garden A', 20);")
        weak = _chunk("chunk-3", 0.470439)
        selected = select_context_chunks([top, call, weak], minimum_similarity=0.50, maximum_similarity_drop=0.06)
        self.assertEqual(selected, [top, call])

    def test_weak_chunks_are_excluded_and_order_is_preserved(self):
        first = _chunk("chunk-1", 0.70)
        second = _chunk("chunk-2", 0.66)
        weak = _chunk("chunk-3", 0.49)
        selected = select_context_chunks([first, second, weak], minimum_similarity=0.50, maximum_similarity_drop=0.06)
        self.assertEqual(selected, [first, second])

    def test_generate_selects_evidence_without_second_retrieval(self):
        top = _chunk("chunk-1", 0.70)
        support = _chunk("chunk-2", 0.66)
        weak = _chunk("chunk-3", 0.45)
        state = {"question": "Question", "retrieved_chunks": [top, support, weak], "mode": "query"}
        with patch("app.graph.nodes.llm_service.generate", new=AsyncMock(return_value="Answer")) as generate:
            result = asyncio.run(generate_node(state))
        generate.assert_awaited_once()
        self.assertEqual(result["selected_chunks"], [top, support])
        self.assertEqual(result["context_chunks"], [top, support])
        self.assertEqual(state["retrieved_chunks"], [top, support, weak])

    def test_question_level_threshold_stays_at_calibrated_value(self):
        self.assertEqual(settings.RELEVANCE_THRESHOLD, 0.55)
