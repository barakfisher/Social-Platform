"""Load a web page again without taking the old version out of use (owner decisions).

"Load again" creates a hidden staging copy (`replaces_id` set) that is fetched and
extracted by the normal job. Staging copies never become Ready, so retrieval keeps using
the original. Unchanged text changes nothing but the load time. Changed text waits for the
owner, who sees the new and removed paragraphs and chooses:
- replace: the new text and its chunks take the original's place;
- append: only paragraphs the source does not have yet are added under a dated heading,
  and nothing is removed (a news page keeps yesterday's items);
- keep: the staging copy is dropped.
A searchable original is updated only after the new chunks are embedded, in one
transaction (`apply`). Each chunk carries added_on, so the writer prefers newer text.
"""

import re
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update

from app.models import KnowledgeChunk, KnowledgeDocument
from app.web_fetch import fallback_title

ACTIVE = ("Pending", "Processing")
AWAITING = "awaiting_decision"
APPEND_HEADING = re.compile(r"^## Added \d{4}-\d{2}-\d{2} / נוסף \d{4}-\d{2}-\d{2}$")
PREVIEW_LIMIT = 30
PREVIEW_CHARACTERS = 500


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def append_heading(day: str) -> str:
    return f"## Added {day} / נוסף {day}"


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


def paragraphs(text: str | None) -> list[str]:
    """Paragraphs as the owner sees them; the headings this module adds are not content."""
    found = []
    for block in re.split(r"\n\s*\n", text or ""):
        block = block.strip()
        if block and not APPEND_HEADING.match(block):
            found.append(block)
    return found


def key(paragraph: str) -> str:
    return " ".join(paragraph.split()).casefold()


def changes(old: str | None, new: str | None) -> tuple[list[str], list[str]]:
    """(paragraphs only in new, paragraphs only in old), in reading order, without repeats."""
    old_keys = {key(p) for p in paragraphs(old)}
    new_keys = {key(p) for p in paragraphs(new)}
    added, seen = [], set()
    for paragraph in paragraphs(new):
        if key(paragraph) not in old_keys and key(paragraph) not in seen:
            seen.add(key(paragraph))
            added.append(paragraph)
    removed = [p for p in paragraphs(old) if key(p) not in new_keys]
    return added, removed


def preview(old: str | None, new: str | None) -> dict:
    added, removed = changes(old, new)

    def clip(items):
        return [p[:PREVIEW_CHARACTERS] for p in items[:PREVIEW_LIMIT]]

    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "added": clip(added),
        "removed": clip(removed),
    }


def mark_unchanged(session, original, staging) -> None:
    original.fetched_at = datetime.now(UTC)
    original.refresh_result = "unchanged"
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))


def keep(session, original, staging) -> str | None:
    """Drops the staging copy; returns its stored page to remove after commit."""
    original.refresh_result = "kept"
    stale_key, staging.storage_key = staging.storage_key, None
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
    return stale_key


def apply(session, original, staging) -> str | None:
    """Applies the owner's choice once the staging chunks are ready; returns the page copy
    the original no longer uses, to remove after commit."""
    if staging.refresh_action == "append":
        return merge(session, original, staging)
    return swap(session, original, staging)


def adopt_page(original, staging) -> str | None:
    replaced_key = original.storage_key
    original.storage_key, staging.storage_key = staging.storage_key, None
    original.fetched_at = staging.fetched_at or datetime.now(UTC)
    return replaced_key if replaced_key != original.storage_key else None


def swap(session, original, staging) -> str | None:
    session.flush()
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == original.id))
    session.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == staging.id)
        .values(document_id=original.id)
    )
    original.source_text = staging.source_text
    if original.title == fallback_title(original.source_reference or ""):
        original.title = staging.title
    original.refresh_result = "replaced"
    if staging.processing_stage == "ready":
        original.status = "Ready"
        original.processing_stage = "ready"
        original.embedding_profile = staging.embedding_profile
    replaced_key = adopt_page(original, staging)
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
    return replaced_key


def merge(session, original, staging) -> str | None:
    """Adds the staging section after the original's text; existing chunks stay as they
    are (and keep their embeddings), the new ones continue the order and offsets."""
    session.flush()
    base_text = original.source_text or ""
    separator = "\n\n" if base_text else ""
    offset = len(base_text) + len(separator)
    last_order = session.scalar(
        select(func.max(KnowledgeChunk.chunk_order)).where(
            KnowledgeChunk.document_id == original.id
        )
    )
    next_order = 0 if last_order is None else last_order + 1
    chunks = session.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == staging.id)
        .order_by(KnowledgeChunk.chunk_order)
    ).all()
    for index, chunk in enumerate(chunks):
        location = dict(chunk.source_location)
        location["char_start"] += offset
        location["char_end"] += offset
        chunk.source_location = location
        chunk.document_id = original.id
        chunk.chunk_order = next_order + index
    original.source_text = base_text + separator + (staging.source_text or "")
    original.refresh_result = "appended"
    replaced_key = adopt_page(original, staging)
    session.flush()
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
    return replaced_key
