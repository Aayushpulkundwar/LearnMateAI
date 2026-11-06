"""persist deterministic assessment evaluations

Revision ID: 0006_assessment_evaluations
Revises: 0005_diagnostic_assessments
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0006_assessment_evaluations"
down_revision = "0005_diagnostic_assessments"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("assessment_evaluations", sa.Column("id", sa.UUID(), nullable=False), sa.Column("attempt_id", sa.UUID(), nullable=False), sa.Column("total_questions", sa.Integer(), nullable=False), sa.Column("correct_count", sa.Integer(), nullable=False), sa.Column("incorrect_count", sa.Integer(), nullable=False), sa.Column("unanswered_count", sa.Integer(), nullable=False), sa.Column("accuracy", sa.Numeric(5,2), nullable=False), sa.Column("chapter_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("topic_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("difficulty_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False), sa.ForeignKeyConstraint(["attempt_id"],["assessment_attempts.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("attempt_id"))
def downgrade(): op.drop_table("assessment_evaluations")
