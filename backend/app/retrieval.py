from datetime import datetime
from typing import cast as typed_cast
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import profile_key
from app.models import KnowledgeChunk, KnowledgeDocument


def documents_first(chunks: list[dict]) -> list[dict]:
    """Each document's best chunk first, then the rest, each by distance.

    A context budget then trims a document's extra chunks before it drops another document
    entirely, however many nearer chunks one long document has (SP-25).
    """
    leads: list[dict] = []
    rest: list[dict] = []
    seen: set[str] = set()
    for chunk in sorted(chunks, key=lambda chunk: chunk["distance"]):
        (rest if chunk["document_id"] in seen else leads).append(chunk)
        seen.add(chunk["document_id"])
    return leads + rest


def relevant_context(
    session: Session,
    vector: list[float],
    *,
    user_id: UUID,
    workspace_id: UUID,
    max_distance: float,
) -> list[dict]:
    """Every chunk within max_distance, each document's best first: relevance alone decides
    what the writer reads; the context budget only caps it (docs/implementation.md)."""
    return documents_first(
        search_context(
            session,
            vector,
            user_id=user_id,
            workspace_id=workspace_id,
            limit=None,
            max_distance=max_distance,
        )
    )


def search_context(
    session: Session,
    vector: list[float],
    *,
    user_id: UUID,
    workspace_id: UUID,
    limit: int | None = 5,
    max_distance: float | None = None,
) -> list[dict]:
    """The nearest chunks within max_distance, nearest first; limit None returns them all."""
    settings = get_settings()
    distance = cast(
        KnowledgeChunk.embedding, Vector(settings.embedding_dimensions)
    ).cosine_distance(vector)
    filters = [
        KnowledgeDocument.workspace_id == workspace_id,
        KnowledgeDocument.user_id == user_id,
        KnowledgeDocument.status == "Ready",
        KnowledgeDocument.embedding_profile == profile_key(),
        KnowledgeChunk.workspace_id == workspace_id,
        KnowledgeChunk.user_id == user_id,
        KnowledgeChunk.embedding_profile == profile_key(),
        KnowledgeChunk.embedding_model == settings.embedding_model,
        KnowledgeChunk.embedding_dimensions == settings.embedding_dimensions,
        KnowledgeChunk.embedding.is_not(None),
    ]
    if max_distance is not None:
        filters.append(distance <= max_distance)
    nearest = (
        select(KnowledgeChunk, KnowledgeDocument.title, KnowledgeDocument.created_at, distance)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(*filters)
        .order_by(distance, KnowledgeChunk.id)
    )
    return rows(session.execute(nearest if limit is None else nearest.limit(limit)).all())


def rows(result) -> list[dict]:
    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "title": title,
            "content": chunk.content,
            # Chunks prepared before added_on existed date from their document's creation.
            "source_location": {
                "added_on": created_at.date().isoformat(),
                **chunk.source_location,
            },
            "distance": float(value),
        }
        for chunk, title, created_at, value in typed_cast(
            list[tuple[KnowledgeChunk, str, datetime, float]], result
        )
    ]
