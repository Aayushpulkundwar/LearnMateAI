"""Hybrid, metadata-filtered retrieval over pgvector and PostgreSQL FTS."""
from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import func, literal_column, select

from app.core.db import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    document_id: str
    document_title: str
    content: str
    page_number: Optional[int]
    chapter: Optional[str]
    chunk_index: int
    similarity_score: float
    lexical_score: float = 0.0
    vector_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    rrf_score: float = 0.0


def reciprocal_rank_fusion(vector_rows: Iterable[tuple], lexical_rows: Iterable[tuple], *, rrf_k: int = 60) -> list[RetrievedChunk]:
    """Merge independently-ranked candidates without comparing incompatible scores."""
    merged: dict[str, dict] = {}

    def add(rows: Iterable[tuple], source: str) -> None:
        for rank, (chunk, document, score) in enumerate(rows, start=1):
            item = merged.setdefault(str(chunk.id), {"chunk": chunk, "document": document, "similarity": 0.0, "lexical": 0.0, "vector_rank": None, "lexical_rank": None, "rrf": 0.0})
            item["rrf"] += 1.0 / (rrf_k + rank)
            if source == "vector":
                item["similarity"], item["vector_rank"] = float(score), rank
            else:
                item["lexical"], item["lexical_rank"] = float(score), rank

    add(vector_rows, "vector")
    add(lexical_rows, "lexical")
    ranked = sorted(merged.values(), key=lambda item: (-item["rrf"], -item["similarity"], -item["lexical"], str(item["chunk"].id)))
    return [RetrievedChunk(
        str(item["chunk"].id), str(item["chunk"].document_id), item["document"].title,
        item["chunk"].content, item["chunk"].page_number, item["chunk"].chapter,
        item["chunk"].chunk_index, item["similarity"], item["lexical"], item["vector_rank"],
        item["lexical_rank"], item["rrf"],
    ) for item in ranked]


class RetrievalService:
    @staticmethod
    def _apply_filters(statement, *, document_id=None, subject=None, grade=None, chapter=None, grade_id=None, subject_id=None, chapter_id=None, document_ids=None, chunk_ids=None):
        # Research snapshots use explicit allowlists before ranking. An empty
        # list intentionally matches nothing; it must never remove the filter.
        if document_ids is not None:
            statement = statement.where(Chunk.document_id.in_([UUID(str(value)) for value in document_ids]))
        if chunk_ids is not None:
            statement = statement.where(Chunk.id.in_([UUID(str(value)) for value in chunk_ids]))
        if document_id:
            statement = statement.where(Chunk.document_id == UUID(str(document_id)))
        if subject:
            statement = statement.where(Document.subject == subject)
        if grade:
            statement = statement.where(Document.grade == grade)
        if chapter:
            statement = statement.where(Chunk.chapter == chapter)
        if grade_id:
            statement = statement.where(Document.grade_id == UUID(str(grade_id)))
        if subject_id:
            statement = statement.where(Document.subject_id == UUID(str(subject_id)))
        if chapter_id:
            statement = statement.where(Document.chapter_id == UUID(str(chapter_id)))
        return statement

    async def retrieve_chunks(self, query_embedding, *, query_text="", document_id=None, subject=None, grade=None, chapter=None, grade_id=None, subject_id=None, chapter_id=None, top_k=5, candidate_multiplier=4, rrf_k=60, mode="hybrid", document_ids=None, chunk_ids=None):
        """Return dense, lexical, or RRF-ranked candidates in the requested scope.

        ``mode`` is intentionally internal/optional so existing API callers
        retain hybrid retrieval while benchmark jobs can evaluate each signal.
        """
        if mode not in {"dense", "lexical", "hybrid"}:
            raise ValueError("mode must be one of: dense, lexical, hybrid")
        candidate_limit = max(top_k, top_k * candidate_multiplier)
        filters = dict(document_id=document_id, subject=subject, grade=grade, chapter=chapter, grade_id=grade_id, subject_id=subject_id, chapter_id=chapter_id, document_ids=document_ids, chunk_ids=chunk_ids)
        distance = Chunk.embedding.cosine_distance(query_embedding)
        similarity = (1 - distance).label("similarity_score")
        vector_statement = self._apply_filters(select(Chunk, Document, similarity).join(Document).where(Chunk.embedding.is_not(None)), **filters).order_by(distance).limit(candidate_limit)
        vector_rows, lexical_rows = [], []
        async with AsyncSessionLocal() as session:
            if mode != "lexical":
                vector_rows = (await session.execute(vector_statement)).all()
            if mode != "dense" and query_text.strip():
                # Keep this expression byte-for-byte aligned with the GIN index
                # in migration 0010 so PostgreSQL can use it for candidate search.
                search_vector = func.to_tsvector(literal_column("'simple'"), func.coalesce(Chunk.content, literal_column("''")))
                search_query = func.websearch_to_tsquery(literal_column("'simple'"), query_text)
                lexical_score = func.ts_rank_cd(search_vector, search_query, 32).label("lexical_score")
                lexical_statement = self._apply_filters(select(Chunk, Document, lexical_score).join(Document).where(search_vector.op("@@")(search_query)), **filters).order_by(lexical_score.desc(), Chunk.id).limit(candidate_limit)
                lexical_rows = (await session.execute(lexical_statement)).all()
        if mode == "dense":
            return reciprocal_rank_fusion(vector_rows, [], rrf_k=rrf_k)[:top_k]
        if mode == "lexical":
            return reciprocal_rank_fusion([], lexical_rows, rrf_k=rrf_k)[:top_k]
        return reciprocal_rank_fusion(vector_rows, lexical_rows, rrf_k=rrf_k)[:top_k]


retrieval_service = RetrievalService()
