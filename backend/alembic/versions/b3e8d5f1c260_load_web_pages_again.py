"""load web pages again through a hidden staging copy, replacing or appending (SP-9)"""

import sqlalchemy as sa

from alembic import op

revision = "b3e8d5f1c260"
down_revision = "9d4f2a6c8e17"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_documents", sa.Column("replaces_id", sa.Uuid(), nullable=True))
    op.add_column(
        "knowledge_documents",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_documents", sa.Column("refresh_result", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "knowledge_documents", sa.Column("refresh_action", sa.String(length=10), nullable=True)
    )
    op.create_unique_constraint(
        "knowledge_documents_replaces_id_key", "knowledge_documents", ["replaces_id"]
    )
    op.create_foreign_key(
        "fk_knowledge_documents_replaces",
        "knowledge_documents",
        "knowledge_documents",
        ["replaces_id", "workspace_id", "user_id"],
        ["id", "workspace_id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "knowledge_documents_refresh_result",
        "knowledge_documents",
        "refresh_result IN ('unchanged', 'replaced', 'appended', 'kept')",
    )
    op.create_check_constraint(
        "knowledge_documents_refresh_action",
        "knowledge_documents",
        "refresh_action IN ('replace', 'append')",
    )


def downgrade():
    op.drop_constraint("knowledge_documents_refresh_action", "knowledge_documents")
    op.drop_constraint("knowledge_documents_refresh_result", "knowledge_documents")
    op.drop_constraint("fk_knowledge_documents_replaces", "knowledge_documents")
    op.drop_constraint("knowledge_documents_replaces_id_key", "knowledge_documents")
    op.drop_column("knowledge_documents", "refresh_action")
    op.drop_column("knowledge_documents", "refresh_result")
    op.drop_column("knowledge_documents", "fetched_at")
    op.drop_column("knowledge_documents", "replaces_id")
