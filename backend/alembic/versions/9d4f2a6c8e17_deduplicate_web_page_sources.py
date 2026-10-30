"""deduplicate web page sources by normalized URL (SP-9)"""

import sqlalchemy as sa

from alembic import op

revision = "9d4f2a6c8e17"
down_revision = "7b2e4c9d1a35"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_url_workspace_checksum",
        "knowledge_documents",
        ["workspace_id", "checksum"],
        unique=True,
        postgresql_where=sa.text("source_type = 'url' AND checksum IS NOT NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_url_workspace_checksum",
        table_name="knowledge_documents",
        postgresql_where=sa.text("source_type = 'url' AND checksum IS NOT NULL"),
    )
