from typing import cast as typed_cast
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import profile_key
from app.models import KnowledgeChunk, KnowledgeDocument

# With a per-document cap, candidates are drawn from this many times the requested count, so
# a second document's best chunk is found even when one document fills the top ranks (SP-25).
CANDIDATE_POOL_FACTOR = 4


def spread_across_documents(candidates: list[dict], count: int, per_document: int) -> list[dict]:
    """Up to count of the nearest candidates, at most per_document from one document while
    other documents still have candidates; each document's best chunk comes first.

    Candidates arrive nearest first. Chunks held back by the cap fill any slots left over, so
    a Knowledge Base with one relevant document still gets count chunks. Putting each
    document's best chunk first means a tight context budget trims a document's extra chunks
    before it drops another document entirely.
    """
    chosen: list[dict] = []
    held: list[dict] = []
    used: dict[str, int] = {}
    for candidate in candidates:
        if len(chosen) == count:
            break
        document = candidate["document_id"]
        if used.get(document, 0) < per_document:
            chosen.append(candidate)
            used[document] = used.get(document, 0) + 1
        else:
            held.append(candidate)
    chosen += held[: count - len(chosen)]
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
    pool = limit * CANDIDATE_POOL_FACTOR if per_document is not None else limit
    rows = session.execute(query.order_by(distance, KnowledgeChunk.id).limit(pool)).all()
    found = [
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
    if per_document is None:
        return found
    return spread_across_documents(found, limit, per_document)
