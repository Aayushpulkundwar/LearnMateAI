"""Add the full-text index used by hybrid retrieval.

Revision ID: 0010_hybrid_retrieval_fts
Revises: 0009_document_curriculum_links
"""

from alembic import op


revision = "0010_hybrid_retrieval_fts"
down_revision = "0009_document_curriculum_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_content_fts "
        "ON chunks USING gin (to_tsvector('simple', coalesce(content, '')))"
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_content_fts", table_name="chunks")
