"""Load a web page again without taking the old version out of use (owner decision).

"Load again" creates a hidden staging copy (`replaces_id` set) that goes through the normal
fetch, extraction and embedding jobs. Staging copies never become Ready, so retrieval keeps
using the original. When the staging copy is complete, `swap` moves its chunks onto the
original in one transaction and deletes it. Unchanged text changes nothing but the time.
"""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from app.models import KnowledgeChunk, KnowledgeDocument
from app.web_fetch import fallback_title

ACTIVE = ("Pending", "Processing")


def staging_for(session, original_id, lock: bool = False):
    query = select(KnowledgeDocument).where(KnowledgeDocument.replaces_id == original_id)
    return session.scalar(query.with_for_update() if lock else query)


def lock_original(session, staging_id):
    """Lock order for every refresh write: the original first, then its staging copy."""
    original_id = session.scalar(
        select(KnowledgeDocument.replaces_id).where(KnowledgeDocument.id == staging_id)
    )
    if original_id is None:
        return None
    return session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.id == original_id).with_for_update()
    )


def mark_unchanged(session, original, staging) -> None:
    original.fetched_at = datetime.now(UTC)
    original.refresh_result = "unchanged"
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))


def swap(session, original, staging) -> str | None:
    """Puts the staging copy's text and chunks on the original; returns the replaced
    page's storage key, to remove after commit."""
    session.flush()
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == original.id))
    session.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == staging.id)
        .values(document_id=original.id)
    )
    replaced_key = original.storage_key
    original.source_text = staging.source_text
    original.storage_key, staging.storage_key = staging.storage_key, None
    if original.title == fallback_title(original.source_reference or ""):
        original.title = staging.title
    original.fetched_at = staging.fetched_at or datetime.now(UTC)
    original.refresh_result = "updated"
    if staging.processing_stage == "ready":
        original.status = "Ready"
        original.processing_stage = "ready"
        original.embedding_profile = staging.embedding_profile
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
    return replaced_key if replaced_key != original.storage_key else None
