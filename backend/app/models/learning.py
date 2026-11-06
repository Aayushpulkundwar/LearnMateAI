"""Relational learning-domain models for assessments and student analytics.

These models intentionally keep answer-key data in the persistence layer only.
Public response schemas must project questions/options without ``is_correct``.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


UTC_NOW = text("timezone('utc', now())")


class User(Base):
    """Minimal identity anchor; authentication fields can be added independently."""

    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), nullable=True, unique=True, index=True)
    password_hash = Column(String(512), nullable=True)
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=_utcnow)
    student = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")


class Grade(Base):
    __tablename__ = "grades"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True)
    students = relationship("Student", back_populates="grade")
    subjects = relationship("Subject", back_populates="grade")


class Student(Base):
    __tablename__ = "students"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=_utcnow)
    user = relationship("User", back_populates="student")
    grade = relationship("Grade", back_populates="students")
    attempts = relationship("AssessmentAttempt", back_populates="student")
    topic_masteries = relationship("TopicMastery", back_populates="student")
    mastery_history = relationship("MasteryHistory", back_populates="student")
    recommendations = relationship("LearningRecommendation", back_populates="student")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    user = relationship("User", back_populates="sessions")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("grade_id", "name", name="uq_subjects_grade_name"),
        UniqueConstraint("id", "grade_id", name="uq_subjects_id_grade"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column(Text, nullable=True)
    grade = relationship("Grade", back_populates="subjects")
    chapters = relationship("Chapter", back_populates="subject")
    questions = relationship("Question", back_populates="subject")
    assessments = relationship("Assessment", back_populates="subject")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("subject_id", "chapter_number", name="uq_chapters_subject_number"),
        UniqueConstraint("id", "subject_id", name="uq_chapters_id_subject"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    subject = relationship("Subject", back_populates="chapters")
    topics = relationship("Topic", back_populates="chapter")
    questions = relationship("Question", back_populates="chapter")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("chapter_id", "name", name="uq_topics_chapter_name"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    chapter = relationship("Chapter", back_populates="topics")
    questions = relationship("Question", back_populates="topic")
    masteries = relationship("TopicMastery", back_populates="topic")
    mastery_history = relationship("MasteryHistory", back_populates="topic")
    recommendations = relationship("LearningRecommendation", back_populates="topic")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_questions_difficulty"),
        CheckConstraint("validation_status IN ('draft', 'validated', 'review', 'rejected')", name="ck_questions_validation_status"),
        UniqueConstraint("question_fingerprint", name="uq_questions_fingerprint"),
        Index("ix_questions_curriculum_validated", "subject_id", "chapter_id", "topic_id", "validation_status"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_fingerprint = Column(String(64), nullable=False)
    assessment_metadata = Column(JSONB, nullable=True)
    difficulty = Column(String(20), nullable=False)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    source_page = Column(Integer, nullable=True)
    source_chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    explanation = Column(Text, nullable=True)
    validation_status = Column(String(20), nullable=False, server_default="draft")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    subject = relationship("Subject", back_populates="questions")
    chapter = relationship("Chapter", back_populates="questions")
    topic = relationship("Topic", back_populates="questions")
    source_document = relationship("Document", back_populates="questions")
    source_chunk = relationship("Chunk", back_populates="questions")
    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan")
    attempt_questions = relationship("AttemptQuestion", back_populates="question")


class QuestionGenerationJob(Base):
    __tablename__ = "question_generation_jobs"
    __table_args__ = (CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_question_generation_jobs_status"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_count = Column(Integer, nullable=False)
    difficulty_distribution = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")
    generated_count = Column(Integer, nullable=False, server_default="0")
    rejected_count = Column(Integer, nullable=False, server_default="0")
    error_message = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("id", "question_id", name="uq_question_options_id_question"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    option_text = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False, server_default=text("false"))
    misconception_tag = Column(String(255), nullable=True)
    question = relationship("Question", back_populates="options")
    selected_answers = relationship("StudentAnswer", back_populates="selected_option")


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("assessment_type IN ('diagnostic', 'practice', 'reassessment')", name="ck_assessments_type"),
        CheckConstraint("question_count > 0", name="ck_assessments_question_count"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    assessment_type = Column(String(30), nullable=False)
    question_count = Column(Integer, nullable=False)
    coverage_warning = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    subject = relationship("Subject", back_populates="assessments")
    attempts = relationship("AssessmentAttempt", back_populates="assessment")


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="ck_assessment_attempts_status"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_assessment_attempts_score"),
        Index("ix_assessment_attempts_student_status", "student_id", "status"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="in_progress")
    score = Column(Numeric(5, 2), nullable=True)
    assessment = relationship("Assessment", back_populates="attempts")
    student = relationship("Student", back_populates="attempts")
    attempt_questions = relationship("AttemptQuestion", back_populates="attempt", cascade="all, delete-orphan")
    mastery_history = relationship("MasteryHistory", back_populates="assessment_attempt")
    evaluation_result = relationship("AssessmentEvaluation", back_populates="attempt", uselist=False, cascade="all, delete-orphan")


class AssessmentEvaluation(Base):
    __tablename__ = "assessment_evaluations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_questions = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    incorrect_count = Column(Integer, nullable=False)
    unanswered_count = Column(Integer, nullable=False)
    accuracy = Column(Numeric(5, 2), nullable=False)
    chapter_results = Column(JSONB, nullable=False)
    topic_results = Column(JSONB, nullable=False)
    difficulty_results = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    attempt = relationship("AssessmentAttempt", back_populates="evaluation_result")


class AttemptQuestion(Base):
    __tablename__ = "attempt_questions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "display_order", name="uq_attempt_questions_attempt_order"),
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_questions_attempt_question"),
        UniqueConstraint("id", "question_id", name="uq_attempt_questions_id_question"),
        CheckConstraint("display_order > 0", name="ck_attempt_questions_display_order"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False, index=True)
    display_order = Column(Integer, nullable=False)
    option_order_snapshot = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    attempt = relationship("AssessmentAttempt", back_populates="attempt_questions")
    question = relationship("Question", back_populates="attempt_questions")
    student_answer = relationship(
        "StudentAnswer",
        back_populates="attempt_question",
        uselist=False,
        cascade="all, delete-orphan",
        overlaps="selected_answers,selected_option",
    )


class StudentAnswer(Base):
    __tablename__ = "student_answers"
    __table_args__ = (
        UniqueConstraint("attempt_question_id", name="uq_student_answers_attempt_question"),
        ForeignKeyConstraint(["attempt_question_id", "question_id"], ["attempt_questions.id", "attempt_questions.question_id"], name="fk_student_answers_attempt_question", ondelete="CASCADE"),
        ForeignKeyConstraint(["selected_option_id", "question_id"], ["question_options.id", "question_options.question_id"], name="fk_student_answers_option_question", ondelete="RESTRICT"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_question_id = Column(UUID(as_uuid=True), nullable=False)
    question_id = Column(UUID(as_uuid=True), nullable=False)
    selected_option_id = Column(UUID(as_uuid=True), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    attempt_question = relationship(
        "AttemptQuestion",
        back_populates="student_answer",
        overlaps="selected_answers,selected_option",
    )
    selected_option = relationship(
        "QuestionOption",
        back_populates="selected_answers",
        overlaps="attempt_question,student_answer",
    )


class TopicMastery(Base):
    __tablename__ = "topic_mastery"
    __table_args__ = (
        UniqueConstraint("student_id", "topic_id", name="uq_topic_mastery_student_topic"),
        CheckConstraint("mastery_score >= 0 AND mastery_score <= 100", name="ck_topic_mastery_score"),
        CheckConstraint("evidence_count >= 0", name="ck_topic_mastery_evidence_count"),
        Index("ix_topic_mastery_student_score", "student_id", "mastery_score"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    mastery_score = Column(Numeric(5, 2), nullable=False)
    confidence_level = Column(String(30), nullable=False)
    evidence_count = Column(Integer, nullable=False, server_default="0")
    last_assessed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=_utcnow)
    student = relationship("Student", back_populates="topic_masteries")
    topic = relationship("Topic", back_populates="masteries")


class MasteryHistory(Base):
    __tablename__ = "mastery_history"
    __table_args__ = (
        CheckConstraint("previous_score >= 0 AND previous_score <= 100", name="ck_mastery_history_previous_score"),
        CheckConstraint("updated_score >= 0 AND updated_score <= 100", name="ck_mastery_history_updated_score"),
        Index("ix_mastery_history_student_topic_recorded", "student_id", "topic_id", "recorded_at"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    previous_score = Column(Numeric(5, 2), nullable=False)
    updated_score = Column(Numeric(5, 2), nullable=False)
    assessment_attempt_id = Column(UUID(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    student = relationship("Student", back_populates="mastery_history")
    topic = relationship("Topic", back_populates="mastery_history")
    assessment_attempt = relationship("AssessmentAttempt", back_populates="mastery_history")


class LearningRecommendation(Base):
    __tablename__ = "learning_recommendations"
    __table_args__ = (
        CheckConstraint("priority >= 1 AND priority <= 5", name="ck_learning_recommendations_priority"),
        CheckConstraint("status IN ('active', 'dismissed', 'completed')", name="ck_learning_recommendations_status"),
        Index("ix_learning_recommendations_student_status_priority", "student_id", "status", "priority"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_type = Column(String(50), nullable=False)
    priority = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=UTC_NOW)
    student = relationship("Student", back_populates="recommendations")
    topic = relationship("Topic", back_populates="recommendations")
