import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Record:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(200))


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("id", "user_id"),)


class Owned(Record):
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)


def ownership():
    return ForeignKeyConstraint(
        ["workspace_id", "user_id"], ["workspaces.id", "workspaces.user_id"], ondelete="CASCADE"
    )


class BrandDNA(Owned, Base):
    __tablename__ = "brand_dna"
    name: Mapped[str] = mapped_column(String(200))
    audience: Mapped[str] = mapped_column(Text, default="")
    positioning: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(Text, default="")
    guidelines: Mapped[str] = mapped_column(Text, default="")
    prohibited_claims: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (ownership(), UniqueConstraint("workspace_id"), CheckConstraint("version > 0"))


class KnowledgeDocument(Owned, Base):
    __tablename__ = "knowledge_documents"
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(20))
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)
    # Opaque key of the private uploaded file (app/storage.py); None for pasted text.
    storage_key: Mapped[str | None] = mapped_column(String(64))
    processing_stage: Mapped[str] = mapped_column(
        String(30), default="pending", server_default="pending"
    )
    embedding_profile: Mapped[str | None] = mapped_column(String(64))
    checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    # What the owner says the document is: knowledge to draw facts from, or finished posts
    # (app/knowledge.py DocumentKind). Topic ideas never restate a sample post.
    kind: Mapped[str] = mapped_column(String(20), default="knowledge", server_default="knowledge")
    # Set only on a hidden staging copy while a web page is loaded again (app/refresh.py).
    # It never becomes Ready, so retrieval keeps using the original until the swap.
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    # When a web page was last loaded, and how the last "load again" ended.
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_result: Mapped[str | None] = mapped_column(String(20))
    # On a staging copy: the owner's choice for changed text, applied once it is embedded.
    refresh_action: Mapped[str | None] = mapped_column(String(10))
    __table_args__ = (
        ownership(),
        UniqueConstraint("id", "workspace_id", "user_id"),
        ForeignKeyConstraint(
            ["replaces_id", "workspace_id", "user_id"],
            [
                "knowledge_documents.id",
                "knowledge_documents.workspace_id",
                "knowledge_documents.user_id",
            ],
            ondelete="CASCADE",
            name="fk_knowledge_documents_replaces",
        ),
        Index(
            "uq_text_workspace_checksum",
            "workspace_id",
            "checksum",
            unique=True,
            postgresql_where=text("source_type = 'text' AND checksum IS NOT NULL"),
        ),
        # Uploaded files deduplicate on their exact bytes, per type, within a workspace.
        Index(
            "uq_file_workspace_checksum",
            "workspace_id",
            "source_type",
            "checksum",
            unique=True,
            postgresql_where=text("source_type IN ('pdf', 'txt') AND checksum IS NOT NULL"),
        ),
        # A web page is submitted once per workspace, by its normalized URL's checksum.
        Index(
            "uq_url_workspace_checksum",
            "workspace_id",
            "checksum",
            unique=True,
            postgresql_where=text("source_type = 'url' AND checksum IS NOT NULL"),
        ),
        CheckConstraint(
            "source_type IN ('text', 'txt', 'pdf', 'url')",
            name="knowledge_documents_source_type_check",
        ),
        CheckConstraint("status IN ('Pending', 'Processing', 'Ready', 'Failed')"),
        CheckConstraint(
            "refresh_result IN ('unchanged', 'replaced', 'appended', 'kept')",
            name="knowledge_documents_refresh_result",
        ),
        CheckConstraint(
            "refresh_action IN ('replace', 'append')", name="knowledge_documents_refresh_action"
        ),
        CheckConstraint("kind IN ('knowledge', 'sample_posts')", name="knowledge_documents_kind"),
    )


class KnowledgeChunk(Owned, Base):
    __tablename__ = "knowledge_chunks"
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    chunk_order: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    source_location: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Configurable dimensions; profile tags isolate incompatible embedding spaces.
    embedding = mapped_column(Vector(), nullable=True)
    embedding_profile: Mapped[str | None] = mapped_column(String(64), index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ownership(),
        ForeignKeyConstraint(
            ["document_id", "workspace_id", "user_id"],
            [
                "knowledge_documents.id",
                "knowledge_documents.workspace_id",
                "knowledge_documents.user_id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "chunk_order"),
        CheckConstraint("chunk_order >= 0 AND token_count >= 0"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_dimensions IS NULL AND embedding_model IS NULL) "
            "OR (embedding IS NOT NULL AND embedding_dimensions IS NOT NULL "
            "AND embedding_model IS NOT NULL AND vector_dims(embedding) = embedding_dimensions "
            "AND embedding_dimensions > 0)"
        ),
    )


class Post(Owned, Base):
    __tablename__ = "posts_history"
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    save_key: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    generation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generation_runs.id", ondelete="SET NULL"), unique=True
    )
    platform: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(5))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    media_references: Mapped[list] = mapped_column(JSONB, default=list)
    generation_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_snapshots: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = (
        ownership(),
        UniqueConstraint("workspace_id", "save_key"),
        CheckConstraint("version > 0", name="ck_posts_version_positive"),
        CheckConstraint("platform IN ('linkedin', 'facebook')"),
        CheckConstraint("language IN ('en', 'he')"),
        CheckConstraint("status = 'Draft'", name="phase_one_drafts_only"),
        Index("ix_posts_workspace_status_created", "workspace_id", "status", "created_at"),
    )


class IngestionJob(Owned, Base):
    __tablename__ = "ingestion_jobs"
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)
    kind: Mapped[str] = mapped_column(String(30), default="ingestion")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        ownership(),
        Index(
            "uq_embedding_job_document",
            "document_id",
            unique=True,
            postgresql_where=text("kind = 'embedding'"),
        ),
        ForeignKeyConstraint(
            ["document_id", "workspace_id", "user_id"],
            [
                "knowledge_documents.id",
                "knowledge_documents.workspace_id",
                "knowledge_documents.user_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('Pending', 'Processing', 'Ready', 'Failed')"),
        CheckConstraint("attempts >= 0"),
    )


class GenerationRun(Owned, Base):
    __tablename__ = "generation_runs"
    request_key: Mapped[uuid.UUID] = mapped_column(Uuid)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    inputs: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="Processing")
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        ownership(),
        UniqueConstraint("workspace_id", "request_key"),
        CheckConstraint("status IN ('Processing', 'Ready', 'Failed')"),
    )
