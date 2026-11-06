"""add diagnostic coverage warning

Revision ID: 0005_diagnostic_assessments
Revises: 0004_question_bank_engine
"""
from alembic import op
import sqlalchemy as sa
revision = "0005_diagnostic_assessments"
down_revision = "0004_question_bank_engine"
branch_labels = None
depends_on = None
def upgrade(): op.add_column("assessments", sa.Column("coverage_warning", sa.Text(), nullable=True))
def downgrade(): op.drop_column("assessments", "coverage_warning")
