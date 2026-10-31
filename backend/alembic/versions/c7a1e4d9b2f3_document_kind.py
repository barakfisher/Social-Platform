"""mark each Knowledge Base document as knowledge or sample posts (SP-29)"""

import sqlalchemy as sa

from alembic import op

revision = "c7a1e4d9b2f3"
down_revision = "b3e8d5f1c260"
branch_labels = None
depends_on = None


def upgrade():
    # Existing documents become knowledge, the meaning every document had until now.
    op.add_column(
        "knowledge_documents",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="knowledge"),
    )
    op.create_check_constraint(
        "knowledge_documents_kind",
        "knowledge_documents",
        "kind IN ('knowledge', 'sample_posts')",
    )


def downgrade():
    op.drop_constraint("knowledge_documents_kind", "knowledge_documents")
    op.drop_column("knowledge_documents", "kind")
