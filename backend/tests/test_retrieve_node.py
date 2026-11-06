import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from app.graph.nodes import retrieve_node
from app.services.retrieval_service import RetrievedChunk

class RetrieveNodeTests(unittest.TestCase):
    def test_uses_existing_embedding_service_and_forwards_filters(self):
        result = RetrievedChunk("chunk-1", "doc-1", "Document", "Actual content", 2, None, 0, 0.8)
        with patch("app.graph.nodes.embedding_service.get_embedding", new=AsyncMock(return_value=[0.1] * 1024)) as embed, patch("app.graph.nodes.retrieval_service.retrieve_chunks", new=AsyncMock(return_value=[result])) as retrieve:
            state = asyncio.run(retrieve_node({"question": "question", "filters": {"document_id": "doc-1", "subject": "Science", "grade": "10", "chapter": None}}))
        embed.assert_awaited_once_with("question")
        self.assertEqual(state["retrieved_chunks"][0]["document_id"], "doc-1")
        self.assertEqual(state["retrieved_chunks"][0]["similarity_score"], 0.8)
        self.assertEqual(retrieve.await_args.kwargs["subject"], "Science")
        self.assertEqual(retrieve.await_args.kwargs["query_text"], "question")

    def test_empty_retrieval_is_preserved(self):
        with patch("app.graph.nodes.embedding_service.get_embedding", new=AsyncMock(return_value=[0.1] * 1024)), patch("app.graph.nodes.retrieval_service.retrieve_chunks", new=AsyncMock(return_value=[])):
            state = asyncio.run(retrieve_node({"question": "question", "filters": {}}))
        self.assertEqual(state["retrieved_chunks"], [])

    def test_forwards_normalized_curriculum_filters(self):
        result = RetrievedChunk("chunk-1", "doc-1", "Document", "Actual content", 2, None, 0, 0.8)
        with patch("app.graph.nodes.embedding_service.get_embedding", new=AsyncMock(return_value=[0.1] * 1024)), patch("app.graph.nodes.retrieval_service.retrieve_chunks", new=AsyncMock(return_value=[result])) as retrieve:
            asyncio.run(retrieve_node({"question": "question", "filters": {"grade_id": "g", "subject_id": "s", "chapter_id": "c"}}))
        self.assertEqual(retrieve.await_args.kwargs["grade_id"], "g")
        self.assertEqual(retrieve.await_args.kwargs["subject_id"], "s")
        self.assertEqual(retrieve.await_args.kwargs["chapter_id"], "c")
