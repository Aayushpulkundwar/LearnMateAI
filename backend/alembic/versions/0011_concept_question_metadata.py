"""Keep concept generation provenance without changing existing question records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0011_concept_question_metadata'
down_revision = '0010_hybrid_retrieval_fts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('questions', sa.Column('assessment_metadata', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('questions', 'assessment_metadata')
