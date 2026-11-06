"""add question-bank administration and generation jobs

Revision ID: 0004_question_bank_engine
Revises: 0003_auth_and_student_profiles
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_question_bank_engine"
down_revision = "0003_auth_and_student_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("questions", sa.Column("question_fingerprint", sa.String(length=64), nullable=True))
    # Existing questions are retained and deterministically backfilled before
    # the uniqueness/not-null safeguard is enabled.
    op.execute("UPDATE questions SET question_fingerprint = md5(lower(regexp_replace(question_text, '\\W+', ' ', 'g'))) WHERE question_fingerprint IS NULL")
    op.alter_column("questions", "question_fingerprint", nullable=False)
    op.create_unique_constraint("uq_questions_fingerprint", "questions", ["question_fingerprint"])
    op.drop_constraint("ck_questions_validation_status", "questions", type_="check")
    op.create_check_constraint("ck_questions_validation_status", "questions", "validation_status IN ('draft', 'validated', 'review', 'rejected')")
    op.create_table(
        "question_generation_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("chapter_id", sa.UUID(), nullable=False),
        sa.Column("topic_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("difficulty_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("generated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="ck_question_generation_jobs_status"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (("ix_question_generation_jobs_subject_id", "subject_id"), ("ix_question_generation_jobs_chapter_id", "chapter_id"), ("ix_question_generation_jobs_topic_id", "topic_id"), ("ix_question_generation_jobs_document_id", "document_id")):
        op.create_index(name, "question_generation_jobs", [column])


def downgrade() -> None:
    op.drop_table("question_generation_jobs")
    op.drop_constraint("ck_questions_validation_status", "questions", type_="check")
    op.create_check_constraint("ck_questions_validation_status", "questions", "validation_status IN ('draft', 'validated', 'rejected')")
    op.drop_constraint("uq_questions_fingerprint", "questions", type_="unique")
    op.drop_column("questions", "question_fingerprint")
    op.drop_column("users", "is_admin")
