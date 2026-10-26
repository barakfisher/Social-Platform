from typing import cast as typed_cast
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import profile_key
from app.models import KnowledgeChunk, KnowledgeDocument


def search_context(
    session: Session,
    vector: list[float],
    *,
    user_id: UUID,
    workspace_id: UUID,
    limit: int = 5,
    max_distance: float | None = None,
) -> list[dict]:
    settings = get_settings()
    distance = cast(
        KnowledgeChunk.embedding, Vector(settings.embedding_dimensions)
    ).cosine_distance(vector)
    query = (
        select(KnowledgeChunk, KnowledgeDocument.title, distance)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
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
        )
    )
    if max_distance is not None:
        query = query.where(distance <= max_distance)
    rows = session.execute(query.order_by(distance, KnowledgeChunk.id).limit(limit)).all()
    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "title": title,
            "content": chunk.content,
            "source_location": chunk.source_location,
            "distance": float(value),
        }
        for chunk, title, value in typed_cast(list[tuple[KnowledgeChunk, str, float]], rows)
    ]
