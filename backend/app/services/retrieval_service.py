"""Metadata-filtered pgvector cosine retrieval."""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document

@dataclass(frozen=True)
class RetrievedChunk:
    id: str; document_id: str; document_title: str; content: str
    page_number: Optional[int]; chapter: Optional[str]; chunk_index: int; similarity_score: float

class RetrievalService:
    async def retrieve_chunks(self, query_embedding, *, document_id=None, subject=None, grade=None, chapter=None, top_k=5):
        distance = Chunk.embedding.cosine_distance(query_embedding)
        similarity = (1 - distance).label("similarity_score")
        statement = select(Chunk, Document, similarity).join(Document).where(Chunk.embedding.is_not(None))
        if document_id:
            statement = statement.where(Chunk.document_id == UUID(str(document_id)))
        if subject:
            statement = statement.where(Document.subject == subject)
        if grade:
            statement = statement.where(Document.grade == grade)
        if chapter:
            statement = statement.where(Chunk.chapter == chapter)
        statement = statement.order_by(distance).limit(top_k)
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(statement)).all()
        return [RetrievedChunk(str(chunk.id), str(chunk.document_id), document.title, chunk.content, chunk.page_number, chunk.chapter, chunk.chunk_index, float(score)) for chunk, document, score in rows]

retrieval_service = RetrievalService()
