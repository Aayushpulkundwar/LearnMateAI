import asyncio
import unittest

from app.graph.nodes import cite_node, refuse_node
from app.schemas.query import Citation


def _chunk(chunk_id, page, index, score, chapter=None, content="Source text"):
    return {
        "id": chunk_id,
        "document_id": "11111111-1111-1111-1111-111111111111",
        "document_title": "Stored Procedures.pdf",
        "chapter": chapter,
        "page_number": page,
        "chunk_index": index,
        "similarity_score": score,
        "content": content,
    }


class CitationTests(unittest.TestCase):
    def test_citations_preserve_used_chunk_metadata_and_rank_order(self):
        first = _chunk("chunk-a", 2, 3, 0.91, "Stored Procedures")
        second = _chunk("chunk-b", 4, 7, 0.72, None)

        result = asyncio.run(cite_node({"context_chunks": [first, second]}))

        self.assertEqual([c["chunk_id"] for c in result["citations"]], ["chunk-a", "chunk-b"])
        self.assertEqual(result["citations"][0]["page_number"], 2)
        self.assertEqual(result["citations"][0]["chunk_index"], 3)
        self.assertEqual(result["citations"][0]["similarity_score"], 0.91)
        self.assertIsNone(result["citations"][1]["chapter"])

    def test_duplicate_or_budget_excluded_chunks_are_not_cited(self):
        included = _chunk("chunk-a", 2, 3, 0.91)
        excluded = _chunk("chunk-c", 9, 12, 0.2)

        result = asyncio.run(cite_node({"context_chunks": [included, included]}))

        self.assertEqual(len(result["citations"]), 1)
        self.assertNotIn(excluded["id"], [c["chunk_id"] for c in result["citations"]])

    def test_refusal_has_no_answer_support_citations(self):
        result = asyncio.run(refuse_node({"retrieved_chunks": [_chunk("chunk-a", 2, 3, 0.2)]}))
        self.assertEqual(result["citations"], [])

    def test_citation_schema_serializes_real_source_fields(self):
        citation = Citation(
            chunk_id="11111111-1111-1111-1111-111111111112",
            document_id="11111111-1111-1111-1111-111111111111",
            document_title="Stored Procedures.pdf",
            page_number=2,
            chunk_index=3,
            similarity_score=0.91,
            snippet="CALL InsertTree(...)",
        )
        payload = citation.model_dump(mode="json")
        self.assertEqual(payload["chunk_index"], 3)
        self.assertEqual(payload["similarity_score"], 0.91)
