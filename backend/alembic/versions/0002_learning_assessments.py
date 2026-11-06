"""add learning assessments and mastery schema

Revision ID: 0002_learning_assessments
Revises: 0001_initial_schema
Create Date: 2026-10-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_learning_assessments"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "grades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "students",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("grade_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_students_grade_id", "students", ["grade_id"])
    op.create_table(
        "subjects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("grade_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grade_id", "name", name="uq_subjects_grade_name"),
    )
    op.create_index("ix_subjects_grade_id", "subjects", ["grade_id"])
    op.create_table(
        "chapters",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "chapter_number", name="uq_chapters_subject_number"),
    )
    op.create_index("ix_chapters_subject_id", "chapters", ["subject_id"])
    op.create_table(
        "topics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chapter_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "name", name="uq_topics_chapter_name"),
    )
    op.create_index("ix_topics_chapter_id", "topics", ["chapter_id"])
    op.create_table(
        "questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("chapter_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_chunk_id", sa.UUID(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("validation_status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_questions_difficulty"),
        sa.CheckConstraint("validation_status IN ('draft', 'validated', 'rejected')", name="ck_questions_validation_status"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for index_name, column in (("ix_questions_subject_id", "subject_id"), ("ix_questions_chapter_id", "chapter_id"), ("ix_questions_topic_id", "topic_id"), ("ix_questions_source_document_id", "source_document_id"), ("ix_questions_source_chunk_id", "source_chunk_id")):
        op.create_index(index_name, "questions", [column])
    op.create_index("ix_questions_curriculum_validated", "questions", ["subject_id", "chapter_id", "topic_id", "validation_status"])
    op.create_table(
        "question_options",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("misconception_tag", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "question_id", name="uq_question_options_id_question"),
    )
    op.create_index("ix_question_options_question_id", "question_options", ["question_id"])
    op.create_table(
        "assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("assessment_type", sa.String(length=30), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.CheckConstraint("assessment_type IN ('diagnostic', 'practice', 'reassessment')", name="ck_assessments_type"),
        sa.CheckConstraint("question_count > 0", name="ck_assessments_question_count"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessments_subject_id", "assessments", ["subject_id"])
    op.create_table(
        "assessment_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="in_progress", nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_assessment_attempts_score"),
        sa.CheckConstraint("status IN ('in_progress', 'submitted', 'abandoned')", name="ck_assessment_attempts_status"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_attempts_assessment_id", "assessment_attempts", ["assessment_id"])
    op.create_index("ix_assessment_attempts_student_id", "assessment_attempts", ["student_id"])
    op.create_index("ix_assessment_attempts_student_status", "assessment_attempts", ["student_id", "status"])
    op.create_table(
        "attempt_questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("attempt_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("option_order_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.CheckConstraint("display_order > 0", name="ck_attempt_questions_display_order"),
        sa.ForeignKeyConstraint(["attempt_id"], ["assessment_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "display_order", name="uq_attempt_questions_attempt_order"),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_attempt_questions_attempt_question"),
        sa.UniqueConstraint("id", "question_id", name="uq_attempt_questions_id_question"),
    )
    op.create_index("ix_attempt_questions_attempt_id", "attempt_questions", ["attempt_id"])
    op.create_index("ix_attempt_questions_question_id", "attempt_questions", ["question_id"])
    op.create_table(
        "student_answers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("attempt_question_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("selected_option_id", sa.UUID(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["attempt_question_id", "question_id"], ["attempt_questions.id", "attempt_questions.question_id"], name="fk_student_answers_attempt_question", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_option_id", "question_id"], ["question_options.id", "question_options.question_id"], name="fk_student_answers_option_question", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_question_id", name="uq_student_answers_attempt_question"),
    )
    op.create_table(
        "topic_mastery",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("mastery_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("confidence_level", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.CheckConstraint("confidence_level >= 0 AND confidence_level <= 1", name="ck_topic_mastery_confidence"),
        sa.CheckConstraint("evidence_count >= 0", name="ck_topic_mastery_evidence_count"),
        sa.CheckConstraint("mastery_score >= 0 AND mastery_score <= 1", name="ck_topic_mastery_score"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "topic_id", name="uq_topic_mastery_student_topic"),
    )
    op.create_index("ix_topic_mastery_student_id", "topic_mastery", ["student_id"])
    op.create_index("ix_topic_mastery_topic_id", "topic_mastery", ["topic_id"])
    op.create_index("ix_topic_mastery_student_score", "topic_mastery", ["student_id", "mastery_score"])
    op.create_table(
        "mastery_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("previous_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("updated_score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("assessment_attempt_id", sa.UUID(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.CheckConstraint("previous_score >= 0 AND previous_score <= 1", name="ck_mastery_history_previous_score"),
        sa.CheckConstraint("updated_score >= 0 AND updated_score <= 1", name="ck_mastery_history_updated_score"),
        sa.ForeignKeyConstraint(["assessment_attempt_id"], ["assessment_attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mastery_history_student_id", "mastery_history", ["student_id"])
    op.create_index("ix_mastery_history_topic_id", "mastery_history", ["topic_id"])
    op.create_index("ix_mastery_history_assessment_attempt_id", "mastery_history", ["assessment_attempt_id"])
    op.create_index("ix_mastery_history_student_topic_recorded", "mastery_history", ["student_id", "topic_id", "recorded_at"])
    op.create_table(
        "learning_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.CheckConstraint("priority >= 1 AND priority <= 5", name="ck_learning_recommendations_priority"),
        sa.CheckConstraint("status IN ('active', 'dismissed', 'completed')", name="ck_learning_recommendations_status"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_recommendations_student_id", "learning_recommendations", ["student_id"])
    op.create_index("ix_learning_recommendations_topic_id", "learning_recommendations", ["topic_id"])
    op.create_index("ix_learning_recommendations_student_status_priority", "learning_recommendations", ["student_id", "status", "priority"])


def downgrade() -> None:
    op.drop_table("learning_recommendations")
    op.drop_table("mastery_history")
    op.drop_table("topic_mastery")
    op.drop_table("student_answers")
    op.drop_table("attempt_questions")
    op.drop_table("assessment_attempts")
    op.drop_table("assessments")
    op.drop_table("question_options")
    op.drop_table("questions")
    op.drop_table("topics")
    op.drop_table("chapters")
    op.drop_table("subjects")
    op.drop_table("students")
    op.drop_table("grades")
    op.drop_table("users")
