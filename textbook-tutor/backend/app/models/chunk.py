import uuid
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.core.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)
    page_number = Column(Integer, nullable=True)
    chapter = Column(String(255), nullable=True)
    chunk_index = Column(Integer, nullable=False)

    # Relationship to document
    document = relationship("Document", back_populates="chunks")
