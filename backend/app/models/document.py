import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # A subject is meaningful only within a grade and a chapter only within
        # a subject.  The composite FKs below verify those parent-child links;
        # these checks also prevent partially-populated associations.
        CheckConstraint("(grade_id IS NULL) = (subject_id IS NULL)", name="ck_documents_grade_subject_pair"),
        CheckConstraint("chapter_id IS NULL OR subject_id IS NOT NULL", name="ck_documents_chapter_requires_subject"),
        ForeignKeyConstraint(
            ["grade_id", "subject_id"], ["subjects.grade_id", "subjects.id"],
            name="fk_documents_subject_grade", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["subject_id", "chapter_id"], ["chapters.subject_id", "chapters.id"],
            name="fk_documents_chapter_subject", ondelete="RESTRICT",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)
    chapter = Column(String(255), nullable=True)
    # Legacy display/search metadata remains during the transition.  New
    # curriculum-aware workflows should use the normalized foreign keys.
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=True, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=True, index=True)
    curriculum_mapping_note = Column(Text, nullable=True)
    processing_status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    minio_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Relationship to chunks
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="source_document")
    grade_record = relationship("Grade", foreign_keys=[grade_id])
    subject_record = relationship("Subject", foreign_keys=[subject_id])
    chapter_record = relationship("Chapter", foreign_keys=[chapter_id])
