import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)
    chapter = Column(String(255), nullable=True)
    processing_status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    minio_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Relationship to chunks
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
