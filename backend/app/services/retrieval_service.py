"""Hybrid, metadata-filtered retrieval over pgvector and PostgreSQL FTS."""
from dataclasses import dataclass, replace
import re
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import String, and_, func, literal_column, or_, select

from app.core.db import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.retrieval_quality import lexical_query, prioritize_explanations


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
    async def quiz_sources(self, db, scope, chapter_name=None, *, max_chars=9000):
        """Broad textbook sampling needs no query embedding or chat relevance gate.

        Reuse the same normalized authorization filters; interleave chapters
        rather than restricting an All Science quiz to the first document.
        """
        rank = func.row_number().over(
            partition_by=func.coalesce(Chunk.chapter, Document.title),
            order_by=func.md5(func.cast(Chunk.id, String)),
        ).label('source_rank')
        statement = self._apply_filters(
            select(Chunk.id, rank).join(Document).where(
                Document.processing_status == 'completed',
                Chunk.embedding.is_not(None), func.length(Chunk.content) >= 180,
            ), grade_id=scope.grade_id, subject_id=scope.subject_id, document_id=scope.document_id,
        )
        if scope.chapter_id:
            statement = statement.where(or_(
                Document.chapter_id == scope.chapter_id,
                and_(Document.chapter_id.is_(None), func.lower(Chunk.chapter) == (chapter_name or '').lower()),
            ))
        ranked = statement.subquery()
        rows = (await db.execute(select(Chunk, Document).join(Document).join(ranked, ranked.c.id == Chunk.id)
                    .order_by(ranked.c.source_rank, Document.chapter_id, Chunk.chunk_index).limit(36))).all()
        sources, used = [], 0
        for chunk, document in rows:
            # Preserve connected explanations, causes and examples. The former
            # isolated-sentence filter removed the relationships needed for
            # application and analysis. Never manufacture repaired equations.
            content = ' '.join(chunk.content.split())
            from app.services.quiz_quality import corrupted
            if corrupted(content) or len(content) < 180:
                continue
            if len(content) > 1200:
                boundary = max(content.rfind('.', 0, 1200), content.rfind('?', 0, 1200))
                content = content[:boundary + 1] if boundary >= 180 else ''
            if not content:
                continue
            if used + len(content) > max_chars:
                continue
            sources.append((chunk, document, content))
            used += len(content)
        return sources

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

    async def retrieve_chunks(self, query_embedding, *, query_text="", document_id=None, subject=None, grade=None, chapter=None, grade_id=None, subject_id=None, chapter_id=None, top_k=5, candidate_multiplier=4, rrf_k=60, mode="hybrid", document_ids=None, chunk_ids=None, educational=False):
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
        if educational:
            vector_statement = vector_statement.where(Document.processing_status == 'completed')
        vector_rows, lexical_rows, lexical_similarities = [], [], {}
        async with AsyncSessionLocal() as session:
            if mode != "lexical":
                vector_rows = (await session.execute(vector_statement)).all()
            if mode != "dense" and query_text.strip():
                # Keep this expression byte-for-byte aligned with the GIN index
                # in migration 0010 so PostgreSQL can use it for candidate search.
                search_vector = func.to_tsvector(literal_column("'simple'"), func.coalesce(Chunk.content, literal_column("''")))
                search_query = func.websearch_to_tsquery(literal_column("'simple'"), lexical_query(query_text) if educational else query_text)
                lexical_score = func.ts_rank_cd(search_vector, search_query, 32).label("lexical_score")
                lexical_statement = self._apply_filters(select(Chunk, Document, lexical_score).join(Document).where(search_vector.op("@@")(search_query)), **filters).order_by(lexical_score.desc(), Chunk.id).limit(candidate_limit)
                if educational:
                    lexical_statement = lexical_statement.where(Document.processing_status == 'completed', Chunk.embedding.is_not(None)).add_columns(similarity)
                    measured_rows = (await session.execute(lexical_statement)).all()
                    lexical_rows = [tuple(row[:3]) for row in measured_rows]
                    lexical_similarities = {str(row[0].id): float(row[3]) for row in measured_rows}
                else:
                    lexical_rows = (await session.execute(lexical_statement)).all()
        if mode == "dense":
            ranked = reciprocal_rank_fusion(vector_rows, [], rrf_k=rrf_k)
        elif mode == "lexical":
            ranked = reciprocal_rank_fusion([], lexical_rows, rrf_k=rrf_k)
        else:
            ranked = reciprocal_rank_fusion(vector_rows, lexical_rows, rrf_k=rrf_k)
        if educational:
            # Lexical-only candidates still get a real cosine score in citation
            # cards, rather than displaying the "not computed" default of zero.
            ranked = [replace(chunk, similarity_score=lexical_similarities[chunk.id])
                      if chunk.vector_rank is None and chunk.id in lexical_similarities else chunk for chunk in ranked]
        return (prioritize_explanations(ranked, query_text) if educational else ranked)[:top_k]


retrieval_service = RetrievalService()
