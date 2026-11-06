"""add optional student gender

Revision ID: 0008_add_student_gender
Revises: 0007_concept_mastery_scores
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_add_student_gender"
down_revision = "0007_concept_mastery_scores"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("students", sa.Column("gender", sa.String(length=30), nullable=True))

def downgrade():
    op.drop_column("students", "gender")
