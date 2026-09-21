import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.nodes import generate_node, grade_relevance_node
from app.graph.workflow import app_graph
from app.services.grounded_context import build_grounded_context
from app.services.llm_service import OllamaLLMService
from app.services.retrieval_service import RetrievedChunk


def _chunk(content, page, index, chapter=None):
    return {
        "id": f"chunk-{index}",
        "document_id": "document-1",
        "document_title": "Stored Procedures",
        "chapter": chapter,
        "page_number": page,
        "chunk_index": index,
        "content": content,
        "similarity_score": 0.9 - (index * 0.1),
    }


class GroundedContextTests(unittest.TestCase):
    def test_context_preserves_rank_order_and_source_metadata(self):
        chunks = [
            _chunk("First ranked text.", 2, 4, None),
            _chunk("Second ranked text.", 3, 5, "Procedures"),
        ]

        context, used_chunks = build_grounded_context(chunks, 1000)

        self.assertEqual(used_chunks, chunks)
        self.assertLess(context.index("First ranked text."), context.index("Second ranked text."))
        self.assertIn("Page: 2", context)
        self.assertIn("Chunk: 4", context)
        self.assertNotIn("Chapter: None", context)
        self.assertIn("Chapter: Procedures", context)

    def test_context_budget_keeps_highest_ranked_sources_first(self):
        chunks = [
            _chunk("A" * 200, 1, 0),
            _chunk("B" * 200, 2, 1),
        ]

        context, used_chunks = build_grounded_context(chunks, 150)

        self.assertLessEqual(len(context), 150)
        self.assertEqual(used_chunks, [chunks[0]])
        self.assertIn("A", context)
        self.assertNotIn("B" * 10, context)


class GenerationNodeTests(unittest.TestCase):
    def _state(self):
        chunks = [_chunk("CALL InsertTree('Neem', 5, 'Garden A', 20);", 2, 2)]
        return {"question": "How do I call InsertTree?", "retrieved_chunks": chunks, "mode": "query"}

    def test_accepted_generation_calls_llm_with_grounded_prompts(self):
        with patch(
            "app.graph.nodes.llm_service.generate",
            new=AsyncMock(return_value="Call InsertTree with its parameters."),
        ) as generate:
            result = asyncio.run(generate_node(self._state()))

        generate.assert_awaited_once()
        kwargs = generate.await_args.kwargs
        self.assertIn("Student Question: How do I call InsertTree?", kwargs["prompt"])
        self.assertIn("CALL InsertTree", kwargs["prompt"])
        self.assertIn("untrusted reference data", kwargs["system_prompt"])
        self.assertEqual(result["answer"], "Call InsertTree with its parameters.")
        self.assertFalse(result["is_refused"])

    def test_generation_failure_is_propagated_not_replaced_with_sample_answer(self):
        with patch(
            "app.graph.nodes.llm_service.generate",
            new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                asyncio.run(generate_node(self._state()))

    def test_irrelevant_evidence_does_not_require_generation(self):
        result = asyncio.run(grade_relevance_node({"retrieved_chunks": []}))
        self.assertFalse(result["is_relevant"])
        self.assertEqual(result["max_relevance_score"], 0.0)

    def test_compiled_graph_refusal_never_calls_llm(self):
        with patch(
            "app.graph.nodes.embedding_service.get_embedding",
            new=AsyncMock(return_value=[0.1] * 1024),
        ), patch(
            "app.graph.nodes.retrieval_service.retrieve_chunks",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.graph.nodes.llm_service.generate", new=AsyncMock()
        ) as generate:
            result = asyncio.run(app_graph.ainvoke({
                "question": "Explain photosynthesis.", "filters": {},
                "retrieved_chunks": [], "selected_chunks": [], "context_chunks": [], "is_relevant": False,
                "max_relevance_score": 0.0, "answer": "", "citations": [],
                "is_refused": False, "refusal_reason": None, "mode": "query",
            }))

        self.assertTrue(result["is_refused"])
        generate.assert_not_awaited()

    def test_compiled_graph_accepted_path_calls_llm_and_retains_evidence(self):
        retrieved = RetrievedChunk(
            "chunk-2", "document-1", "Stored Procedures",
            "CALL InsertTree('Neem', 5, 'Garden A', 20);", 2, None, 2, 0.9,
        )
        with patch(
            "app.graph.nodes.embedding_service.get_embedding",
            new=AsyncMock(return_value=[0.1] * 1024),
        ), patch(
            "app.graph.nodes.retrieval_service.retrieve_chunks",
            new=AsyncMock(return_value=[retrieved]),
        ), patch(
            "app.graph.nodes.llm_service.generate",
            new=AsyncMock(return_value="Use CALL InsertTree(...)."),
        ) as generate:
            result = asyncio.run(app_graph.ainvoke({
                "question": "How do I call InsertTree?", "filters": {},
                "retrieved_chunks": [], "selected_chunks": [], "context_chunks": [], "is_relevant": False,
                "max_relevance_score": 0.0, "answer": "", "citations": [],
                "is_refused": False, "refusal_reason": None, "mode": "query",
            }))

        generate.assert_awaited_once()
        self.assertEqual(result["retrieved_chunks"][0]["id"], "chunk-2")
        self.assertEqual(result["retrieved_chunks"][0]["page_number"], 2)
        self.assertEqual(result["retrieved_chunks"][0]["similarity_score"], 0.9)
        self.assertEqual(result["context_chunks"][0]["content"], "CALL InsertTree('Neem', 5, 'Garden A', 20);")

    def test_empty_provider_response_is_rejected(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "   "}
        client = MagicMock()
        client.post = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        service = OllamaLLMService(base_url="http://ollama.test", model="llama3.1")

        with patch("app.services.llm_service.httpx.AsyncClient", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "empty generation response"):
                asyncio.run(service.generate("Question", "System"))
