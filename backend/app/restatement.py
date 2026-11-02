"""Whether new text restates the owner's sample posts: the same idea in other words.

Topic ideas drop an idea that restates a sample post (SP-29); a draft that restates one is
shown with a warning, found by shared words and by meaning (docs/implementation.md, "sample
posts in drafts" and "restatement by meaning").
"""

import hashlib
import logging
import re
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import EmbeddingError, embed_texts, profile_key
from app.grounding import without_prefix
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID
from app.models import KnowledgeChunk, KnowledgeDocument, SamplePostLine

logger = logging.getLogger(__name__)

# Two topics this similar (shared words over all words) count as the same idea.
NEAR_DUPLICATE = 0.8
# A topic of three or more words inside another of similar length is the same idea; inside a
# much longer one ("Why volunteers matter" in "... less than donors think") it is not.
CONTAINED_LENGTH_RATIO = 0.75
# Where a sample post's lines and sentences end.
SENTENCE = re.compile(r"[\n.?!]+")
# Where a draft's clauses end: a draft joins a post's lines with colons and semicolons
# ("an insight that surprised me: not everyone who succeeded...").
DRAFT_CLAUSE = re.compile(r"[\n.?!:;]+")
# Fewer words than this are a shared phrase ("not necessarily"), not a post's idea.
RESTATED_MIN_WORDS = 4
# Where a line of a post or a draft sentence ends, for the meaning check.
PASSAGE = re.compile(r"(?<=[.?!:;])\s+|\n+")
# Fewer words than this are not compared by meaning ("Not necessarily.").
PASSAGE_MIN_WORDS = 3
# Similarity (1 − cosine distance) from which a draft sentence restates a sample-post line.
# Measured on four real Hebrew drafts with text-embedding-3-small: all 12 copied or reworded
# sentences scored 0.68–1.0, new sentences at most 0.65 (docs/implementation.md).
MEANING_THRESHOLD = 0.65
# A draft with more restated sentences than this is shown with this many warnings.
MAX_RESTATED_WARNINGS = 3


def topic_words(topic: str) -> frozenset[str]:
    return frozenset(word.casefold() for word in re.findall(r"[^\W_]+", topic))


def same_word(a: str, b: str) -> bool:
    # A one-letter Hebrew prefix does not make a different word ("המנטורינג", "מנטורינג").
    return a == b or without_prefix(a) == b or without_prefix(b) == a


def near_duplicate(a: str, b: str) -> bool:
    """The same idea in other words: most words shared, or a topic of three or more words
    contained in another of similar length. Words match across one Hebrew prefix letter."""
    return same_idea(topic_words(a), topic_words(b))


def same_idea(first: frozenset[str], second: frozenset[str]) -> bool:
    """near_duplicate on word sets already taken from their text."""
    if not first or not second:
        return first == second
    shorter, longer = sorted((first, second), key=len)
    # Both rules need the shorter set to be at least this share of the longer one: shared
    # words cannot outnumber the shorter set, nor the union fall below the longer one.
    if len(shorter) / len(longer) < min(CONTAINED_LENGTH_RATIO, NEAR_DUPLICATE):
        return False
    shared = sum(any(same_word(word, other) for other in longer) for word in shorter)
    union = len(first) + len(second) - shared
    contained = (
        len(shorter) >= 3
        and shared == len(shorter)
        and len(shorter) / len(longer) >= CONTAINED_LENGTH_RATIO
    )
    return contained or shared / union >= NEAR_DUPLICATE


def sample_post_lines() -> set[frozenset[str]]:
    """The words of every line and sentence of every Ready sample-posts document, each
    distinct line once: text that restates one offers a finished post back as new."""
    with SessionLocal() as session:
        contents = session.scalars(
            select(KnowledgeChunk.content)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.user_id == LOCAL_USER_ID,
                KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID,
                KnowledgeDocument.status == "Ready",
                KnowledgeDocument.embedding_profile == profile_key(),
                KnowledgeDocument.kind == "sample_posts",
                KnowledgeChunk.user_id == LOCAL_USER_ID,
                KnowledgeChunk.workspace_id == LOCAL_WORKSPACE_ID,
            )
        ).all()
    lines = {topic_words(line) for content in contents for line in SENTENCE.split(content)}
    return lines - {frozenset()}


def restated_sentences(content: str, lines: set[frozenset[str]]) -> list[str]:
    """The draft's clauses that restate a sample-post line, in draft order."""
    restated = []
    for clause in DRAFT_CLAUSE.split(content):
        words = topic_words(clause)
        if len(words) >= RESTATED_MIN_WORDS and any(same_idea(words, line) for line in lines):
            restated.append(clause.strip())
    return restated


def post_lines(text: str) -> list[str]:
    """The lines and sentences of a post worth comparing, in order, without hashtag lines."""
    lines = [line.strip() for line in PASSAGE.split(text)]
    return [
        line
        for line in lines
        if len(line.split()) >= PASSAGE_MIN_WORDS and not line.startswith("#")
    ]


def passages(text: str) -> list[str]:
    """Each line of a sample post and each pair of adjacent lines, once: a draft sentence
    often joins two lines of a post."""
    lines = post_lines(text)
    pairs = [f"{first} {second}" for first, second in zip(lines, lines[1:], strict=False)]
    return list(dict.fromkeys(lines + pairs))


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def missing_passages(document: KnowledgeDocument, stored: set[str]) -> dict[str, str]:
    """The document's passages, by hash, that have no vector in the current profile."""
    wanted = {content_hash(p): p for p in passages(document.source_text or "")}
    return {key: p for key, p in wanted.items() if key not in stored}


def stored_hashes(session, document_id: UUID) -> set[str]:
    return set(
        session.scalars(
            select(SamplePostLine.content_hash).where(
                SamplePostLine.document_id == document_id,
                SamplePostLine.embedding_profile == profile_key(),
            )
        )
    )


def ensure_line_vectors(document_id: UUID) -> int:
    """Embeds the passages of a Ready sample-posts document that have no vector yet and
    removes the ones its text no longer has; returns how many were embedded."""
    profile = profile_key()
    with SessionLocal.begin() as session:
        document = session.get(KnowledgeDocument, document_id)
        if (
            document is None
            or document.kind != "sample_posts"
            or document.status != "Ready"
            or document.embedding_profile != profile
        ):
            return 0
        wanted = {content_hash(p) for p in passages(document.source_text or "")}
        session.execute(
            delete(SamplePostLine).where(
                SamplePostLine.document_id == document_id,
                (SamplePostLine.embedding_profile != profile)
                | SamplePostLine.content_hash.not_in(wanted),
            )
        )
        missing = list(missing_passages(document, stored_hashes(session, document_id)).items())
        owner = (document.user_id, document.workspace_id)
    batch_size = get_settings().embedding_batch_size
    embedded = 0
    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        # No transaction is held while contacting the provider.
        vectors = embed_texts([content for _, content in batch])
        with SessionLocal.begin() as session:
            if session.get(KnowledgeDocument, document_id) is None:
                return embedded
            session.execute(
                insert(SamplePostLine)
                .values(
                    [
                        {
                            "user_id": owner[0],
                            "workspace_id": owner[1],
                            "document_id": document_id,
                            "content": content,
                            "content_hash": key,
                            "embedding": vector,
                            "embedding_profile": profile,
                        }
                        for (key, content), vector in zip(batch, vectors, strict=True)
                    ]
                )
                .on_conflict_do_nothing()
            )
        embedded += len(batch)
    return embedded


def documents_missing_lines() -> list[UUID]:
    """Ready sample-posts documents, in any workspace, with a passage that has no vector."""
    with SessionLocal() as session:
        documents = session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.kind == "sample_posts",
                KnowledgeDocument.status == "Ready",
                KnowledgeDocument.embedding_profile == profile_key(),
            )
        ).all()
        return [
            document.id
            for document in documents
            if missing_passages(document, stored_hashes(session, document.id))
        ]


def dispatch_sample_lines(document_id: UUID) -> None:
    from app.worker import embed_sample_lines

    try:
        embed_sample_lines.apply_async(args=[str(document_id)])
    except Exception:
        # The minute check (app/reconcile.py) queues it again.
        logger.warning("sample_lines_dispatch_failed", extra={"document_id": str(document_id)})


def restated_by_meaning(content: str) -> list[str]:
    """The draft's sentences close in meaning to a line of the workspace's Ready sample
    posts. Empty when no line has a vector yet or the embedding fails: the word check still
    runs, and a draft is never held back by this one."""
    sentences = post_lines(content)
    profile = profile_key()
    in_scope = (
        SamplePostLine.user_id == LOCAL_USER_ID,
        SamplePostLine.workspace_id == LOCAL_WORKSPACE_ID,
        SamplePostLine.embedding_profile == profile,
        KnowledgeDocument.kind == "sample_posts",
        KnowledgeDocument.status == "Ready",
    )
    lines = (
        select(SamplePostLine.embedding)
        .join(KnowledgeDocument, KnowledgeDocument.id == SamplePostLine.document_id)
        .where(*in_scope)
    )
    with SessionLocal() as session:
        if not sentences or session.scalar(lines.limit(1)) is None:
            return []
    batch_size = get_settings().embedding_batch_size
    try:
        vectors = [
            vector
            for start in range(0, len(sentences), batch_size)
            for vector in embed_texts(sentences[start : start + batch_size])
        ]
    except EmbeddingError as exc:
        logger.warning("restatement_embedding_failed", extra={"code": exc.code})
        return []
    restated = []
    dimensions = get_settings().embedding_dimensions
    with SessionLocal() as session:
        for sentence, vector in zip(sentences, vectors, strict=True):
            distance = cast(SamplePostLine.embedding, Vector(dimensions)).cosine_distance(vector)
            nearest = session.scalar(
                select(func.min(distance))
                .join(KnowledgeDocument, KnowledgeDocument.id == SamplePostLine.document_id)
                .where(*in_scope)
            )
            if nearest is not None and 1 - nearest >= MEANING_THRESHOLD:
                restated.append(sentence)
    return restated
