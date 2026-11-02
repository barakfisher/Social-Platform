"""sync shared Google Drive folders into the Knowledge Base (SP-30)"""

import sqlalchemy as sa

from alembic import op

revision = "cd0e430e946f"
down_revision = "d4f2a8c6e1b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drive_folders",
        sa.Column("folder_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('knowledge', 'sample_posts')", name="drive_folders_kind"),
        sa.CheckConstraint(
            "sync_status IN ('Pending', 'Syncing', 'Ready', 'Failed')",
            name="drive_folders_sync_status",
        ),
        sa.CheckConstraint("file_count >= 0 AND skipped_count >= 0", name="drive_folders_counts"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspaces.id", "workspaces.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "workspace_id", "user_id"),
        sa.UniqueConstraint("workspace_id", "folder_id"),
    )
    op.create_index(
        op.f("ix_drive_folders_workspace_id"), "drive_folders", ["workspace_id"], unique=False
    )
    op.add_column("knowledge_documents", sa.Column("drive_folder_id", sa.Uuid(), nullable=True))
    op.add_column(
        "knowledge_documents", sa.Column("drive_file_id", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "knowledge_documents", sa.Column("drive_modified_at", sa.String(length=40), nullable=True)
    )
    op.create_index(
        op.f("ix_knowledge_documents_drive_folder_id"),
        "knowledge_documents",
        ["drive_folder_id"],
        unique=False,
    )
    op.create_index(
        "uq_drive_folder_file",
        "knowledge_documents",
        ["drive_folder_id", "drive_file_id"],
        unique=True,
        postgresql_where=sa.text("drive_folder_id IS NOT NULL AND replaces_id IS NULL"),
    )
    op.create_foreign_key(
        "fk_knowledge_documents_drive_folder",
        "knowledge_documents",
        "drive_folders",
        ["drive_folder_id", "workspace_id", "user_id"],
        ["id", "workspace_id", "user_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("knowledge_documents_source_type_check", "knowledge_documents")
    op.create_check_constraint(
        "knowledge_documents_source_type_check",
        "knowledge_documents",
        "source_type IN ('text', 'txt', 'pdf', 'url', 'drive')",
    )
    op.create_check_constraint(
        "knowledge_documents_drive_file",
        "knowledge_documents",
        "source_type <> 'drive' OR (drive_folder_id IS NOT NULL AND drive_file_id IS NOT NULL)",
    )


def downgrade():
    # Drive sources cannot exist without their folder; they go with the feature.
    op.execute("DELETE FROM knowledge_documents WHERE source_type = 'drive'")
    op.drop_constraint("knowledge_documents_drive_file", "knowledge_documents")
    op.drop_constraint("knowledge_documents_source_type_check", "knowledge_documents")
    op.create_check_constraint(
        "knowledge_documents_source_type_check",
        "knowledge_documents",
        "source_type IN ('text', 'txt', 'pdf', 'url')",
    )
    op.drop_constraint("fk_knowledge_documents_drive_folder", "knowledge_documents")
    op.drop_index(
        "uq_drive_folder_file",
        table_name="knowledge_documents",
        postgresql_where=sa.text("drive_folder_id IS NOT NULL AND replaces_id IS NULL"),
    )
    op.drop_index(op.f("ix_knowledge_documents_drive_folder_id"), table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "drive_modified_at")
    op.drop_column("knowledge_documents", "drive_file_id")
    op.drop_column("knowledge_documents", "drive_folder_id")
    op.drop_index(op.f("ix_drive_folders_workspace_id"), table_name="drive_folders")
    op.drop_table("drive_folders")
