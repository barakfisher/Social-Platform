from datetime import datetime
from typing import cast as typed_cast
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import profile_key
from app.models import KnowledgeChunk, KnowledgeDocument


def spread_across_documents(capped: list[dict], nearest: list[dict], count: int) -> list[dict]:
    """Up to count chunks: the capped selection, filled up from the nearest overall, with
    each document's best chunk first.

    capped holds the nearest chunks with at most the per-document cap from any document;
    nearest holds the nearest chunks with no cap. Filling from nearest only happens when
    capped runs short, which means no other document has a chunk within the limit, so a
    Knowledge Base with one relevant document still gets count chunks. Putting each
    document's best chunk first means a tight context budget trims a document's extra chunks
    before it drops another document entirely.
    """
    chosen = list(capped)
    taken = {candidate["chunk_id"] for candidate in chosen}
    chosen += [c for c in nearest if c["chunk_id"] not in taken][: count - len(chosen)]
    chosen.sort(key=lambda candidate: candidate["distance"])
    seen: set[str] = set()
    leads: list[dict] = []
    rest: list[dict] = []
    for candidate in chosen:
        (rest if candidate["document_id"] in seen else leads).append(candidate)
        seen.add(candidate["document_id"])
    return leads + rest


def search_context(
    session: Session,
    vector: list[float],
    *,
    user_id: UUID,
    workspace_id: UUID,
    limit: int = 5,
    max_distance: float | None = None,
    per_document: int | None = None,
) -> list[dict]:
    """The nearest chunks within max_distance, or, with per_document, at most that many from
    one document while other documents still have chunks within the limit (SP-25)."""
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
    found = rows(session.execute(nearest.limit(limit)).all())
    if per_document is None:
        return found
    # Each chunk's rank within its own document, so the cap applies however many nearer
    # chunks one long document has.
    ranked = (
        select(
            KnowledgeChunk.id.label("id"),
            distance.label("distance"),
            func.row_number()
            .over(partition_by=KnowledgeChunk.document_id, order_by=(distance, KnowledgeChunk.id))
            .label("rank"),
        )
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(*filters)
        .subquery()
    )
    capped_ids = (
        select(ranked.c.id)
        .where(ranked.c.rank <= per_document)
        .order_by(ranked.c.distance, ranked.c.id)
        .limit(limit)
    )
    capped = rows(session.execute(nearest.where(KnowledgeChunk.id.in_(capped_ids))).all())
    return spread_across_documents(capped, found, limit)


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
