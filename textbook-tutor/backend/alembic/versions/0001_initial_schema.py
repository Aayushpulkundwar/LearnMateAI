"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-09 20:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure vector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        'documents',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('grade', sa.String(length=50), nullable=True),
        sa.Column('chapter', sa.String(length=255), nullable=True),
        sa.Column('processing_status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('minio_path', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'chunks',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True),
        sa.Column('document_id', sa.UUID(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('chapter', sa.String(length=255), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('idx_chunks_document_id', 'chunks', ['document_id'])


def downgrade() -> None:
    op.drop_index('idx_chunks_document_id', table_name='chunks')
    op.drop_table('chunks')
    op.drop_table('documents')
