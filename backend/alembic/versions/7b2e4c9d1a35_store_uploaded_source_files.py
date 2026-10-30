"""store uploaded source files privately (SP-9)"""

import sqlalchemy as sa

from alembic import op

revision = "7b2e4c9d1a35"
down_revision = "04825b5fcc24"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_documents", sa.Column("storage_key", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_file_workspace_checksum",
        "knowledge_documents",
        ["workspace_id", "source_type", "checksum"],
        unique=True,
        postgresql_where=sa.text("source_type IN ('pdf', 'txt') AND checksum IS NOT NULL"),
    )
    op.drop_constraint("knowledge_documents_source_type_check", "knowledge_documents")
    op.create_check_constraint(
        "knowledge_documents_source_type_check",
        "knowledge_documents",
        "source_type IN ('text', 'txt', 'pdf', 'url')",
    )


def downgrade():
    op.drop_constraint("knowledge_documents_source_type_check", "knowledge_documents")
    op.create_check_constraint(
        "knowledge_documents_source_type_check",
        "knowledge_documents",
        "source_type IN ('text', 'pdf', 'url')",
    )
    op.drop_index(
        "uq_file_workspace_checksum",
        table_name="knowledge_documents",
        postgresql_where=sa.text("source_type IN ('pdf', 'txt') AND checksum IS NOT NULL"),
    )
    op.drop_column("knowledge_documents", "storage_key")
