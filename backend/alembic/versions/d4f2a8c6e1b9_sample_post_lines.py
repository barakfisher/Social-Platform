"""embedded lines of sample-posts documents, to find a draft that restates one"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "d4f2a8c6e1b9"
down_revision = "c7a1e4d9b2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sample_post_lines",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_profile", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "workspace_id", "user_id"],
            [
                "knowledge_documents.id",
                "knowledge_documents.workspace_id",
                "knowledge_documents.user_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"], ["workspaces.id", "workspaces.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "content_hash", "embedding_profile"),
    )
    op.create_index(op.f("ix_sample_post_lines_document_id"), "sample_post_lines", ["document_id"])
    op.create_index(
        op.f("ix_sample_post_lines_workspace_id"), "sample_post_lines", ["workspace_id"]
    )
    # Existing sample-posts documents get their lines from the minute check after deploy.


def downgrade():
    op.drop_index(op.f("ix_sample_post_lines_workspace_id"), table_name="sample_post_lines")
    op.drop_index(op.f("ix_sample_post_lines_document_id"), table_name="sample_post_lines")
    op.drop_table("sample_post_lines")
