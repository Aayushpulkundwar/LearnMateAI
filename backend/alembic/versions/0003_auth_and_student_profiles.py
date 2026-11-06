"""add authentication credentials sessions and student profile name

Revision ID: 0003_auth_and_student_profiles
Revises: 0002_learning_assessments
Create Date: 2026-10-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_auth_and_student_profiles"
down_revision = "0002_learning_assessments"
branch_labels = None
depends_on = None


UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    # Nullable credentials preserve any pre-auth user records. Authentication
    # endpoints only accept accounts that have a password hash.
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.add_column("students", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_column("students", "display_name")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
