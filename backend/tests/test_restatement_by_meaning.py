# ruff: noqa: F811  (pytest fixtures imported by name)
"""A draft sentence that restates a sample post in other words is found by meaning
(docs/implementation.md, "restatement by meaning")."""

import math
from contextlib import nullcontext
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.embeddings import EmbeddingError, profile_key
from app.local_scope import LOCAL_USER_ID
from app.models import KnowledgeDocument, SamplePostLine, Workspace
from app.reconcile import requeue_sample_lines
from app.restatement import (
    MAX_RESTATED_WARNINGS,
    MEANING_THRESHOLD,
    ensure_line_vectors,
    passages,
)
from app.worker import embed_document, embed_sample_lines
from tests.test_embeddings import (  # noqa: F401  (fixtures used by name)
    embedding_key,
    embedding_settings,
    prepare,
    provider,
)
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    payload,
    service_api,
    settings,
    setup_brand,
    setup_source,
)
from tests.test_retrieval import at_distance

POST = "Not everyone who succeeded can mentor.\nA mentor asks before advising.\n#mentoring"
LINES = ["Not everyone who succeeded can mentor.", "A mentor asks before advising."]
# Just inside and just outside the threshold, as cosine distances from a stored line.
RESTATED = at_distance(1 - MEANING_THRESHOLD - 0.001)
NEW = at_distance(1 - MEANING_THRESHOLD + 0.001)
LINE_VECTOR = [1.0, 0.0, 0.0]


def embed_as(vectors: dict[str, list[float]]):
    """Each text's vector; any other text gets LINE_VECTOR."""
    return lambda texts: [vectors.get(text, LINE_VECTOR) for text in texts]


def sample_document(factory, kind="sample_posts", content=POST) -> UUID:
    setup_source(factory, content=content, title="Posts", kind=kind)
    with factory() as session:
        return session.scalar(
            select(KnowledgeDocument.id).where(KnowledgeDocument.title == "Posts")
        )


def stored(factory, document_id) -> set[str]:
    with factory() as session:
        return set(
            session.scalars(
                select(SamplePostLine.content).where(SamplePostLine.document_id == document_id)
            )
        )


# Passages


def test_passages_are_each_line_and_each_pair_of_adjacent_lines_without_hashtags():
    assert passages(POST) == [*LINES, " ".join(LINES)]
    # Fewer than three words is a phrase, not a line of a post.
    assert passages("Hello there.\n" + LINES[0]) == [LINES[0]]


# Line vectors


def test_line_vectors_are_filled_once_and_follow_the_text(service_api):
    _, factory, _, _ = service_api
    document_id = sample_document(factory)
    with patch("app.restatement.embed_texts", side_effect=embed_as({})) as embed:
        assert ensure_line_vectors(document_id) == 3
        calls = embed.call_count
        assert calls == math.ceil(3 / get_settings().embedding_batch_size)
        assert ensure_line_vectors(document_id) == 0
        assert embed.call_count == calls
    assert stored(factory, document_id) == set(passages(POST))
    changed = LINES[0] + "\nA mentor listens for what is unsaid."
    with factory.begin() as session:
        session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(source_text=changed)
        )
    with patch("app.restatement.embed_texts", side_effect=embed_as({})) as embed:
        assert ensure_line_vectors(document_id) == 2
    assert stored(factory, document_id) == set(passages(changed))


def test_knowledge_documents_get_no_line_vectors(service_api):
    _, factory, _, _ = service_api
    document_id = sample_document(factory, kind="knowledge")
    with patch("app.restatement.embed_texts") as embed:
        assert ensure_line_vectors(document_id) == 0
    embed.assert_not_called()
    assert stored(factory, document_id) == set()


def test_line_vectors_from_another_profile_are_replaced(service_api):
    _, factory, _, _ = service_api
    document_id = sample_document(factory)
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        ensure_line_vectors(document_id)
    with factory.begin() as session:
        session.execute(update(SamplePostLine).values(embedding_profile="old"))
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        assert ensure_line_vectors(document_id) == 3
    with factory() as session:
        profiles = set(session.scalars(select(SamplePostLine.embedding_profile)))
    assert profiles == {profile_key()}


# When lines are filled


def test_marking_a_ready_document_as_sample_posts_fills_its_lines(service_api):
    client, factory, _, _ = service_api
    document_id = sample_document(factory, kind="knowledge")
    with patch("app.knowledge.dispatch_sample_lines") as dispatch:
        assert client.patch(f"/knowledge/{document_id}", json={"kind": "knowledge"}).is_success
        dispatch.assert_not_called()
        response = client.patch(f"/knowledge/{document_id}", json={"kind": "sample_posts"})
    assert response.status_code == 200
    dispatch.assert_called_once_with(document_id)


def test_a_sample_post_document_fills_its_lines_once_embedded(api, provider):
    client, factory, _ = api
    for kind, dispatched in (("sample_posts", True), ("knowledge", False)):
        with (
            patch("app.worker.embed_document.apply_async"),
            patch("app.worker.embedding_lock", return_value=nullcontext(True)),
            patch("app.worker.dispatch_sample_lines") as dispatch,
        ):
            result, job_id = prepare(client, factory, text=f"{kind}: {POST}")
            client.patch(result["status_url"], json={"kind": kind})
            with provider():
                embed_document(job_id)
        assert dispatch.called is dispatched
        if dispatched:
            dispatch.assert_called_once_with(UUID(result["id"]))


def test_the_minute_check_fills_only_documents_missing_lines(service_api):
    _, factory, _, _ = service_api
    complete = sample_document(factory)
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        ensure_line_vectors(complete)
    setup_source(factory, content=POST + "\nOne more line for this one.", title="New posts")
    setup_source(factory, content=POST, title="Notes", kind="knowledge")
    with factory.begin() as session:
        missing = session.scalar(
            select(KnowledgeDocument.id).where(KnowledgeDocument.title == "New posts")
        )
        session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == missing)
            .values(kind="sample_posts")
        )
    with patch("app.reconcile.dispatch_sample_lines") as dispatch:
        assert requeue_sample_lines() == 1
    dispatch.assert_called_once_with(missing)


# Drafts


def draft_with(generation, content: str):
    from tests.test_sample_posts_in_drafts import writer_returns

    writer_returns(generation, content)


def lines_ready(factory, kind="sample_posts") -> UUID:
    document_id = sample_document(factory, kind="sample_posts")
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        ensure_line_vectors(document_id)
    if kind != "sample_posts":
        with factory.begin() as session:
            session.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(kind=kind)
            )
    return document_id


def test_a_sentence_close_in_meaning_to_a_sample_post_line_is_warned(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    lines_ready(factory)
    restated, new = "Success alone does not make a mentor.", "Silence gives people room."
    draft_with(generation, f"{restated} {new}")
    vectors = {restated: RESTATED, new: NEW}
    with patch("app.restatement.embed_texts", side_effect=embed_as(vectors)):
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    assert len(warnings) == 1 and restated.rstrip(".") in warnings[0]


def test_lines_of_a_document_marked_knowledge_again_are_not_compared(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    lines_ready(factory, kind="knowledge")
    restated = "Success alone does not make a mentor."
    draft_with(generation, restated)
    with patch("app.restatement.embed_texts", side_effect=embed_as({})) as embed:
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == []
    embed.assert_not_called()


def test_an_embedding_failure_keeps_the_draft_and_the_word_check(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    lines_ready(factory)
    draft_with(generation, LINES[0] + " Silence gives people room.")
    with patch("app.restatement.embed_texts", side_effect=EmbeddingError("embedding_unavailable")):
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    [warning] = response.json()["warnings"]
    assert "Not everyone who succeeded can mentor" in warning


def test_restated_sentences_are_warned_at_most_a_few_times(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    lines_ready(factory)
    sentences = [f"Restated sentence number {i} here." for i in range(MAX_RESTATED_WARNINGS + 2)]
    draft_with(generation, " ".join(sentences))
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    assert len(warnings) == MAX_RESTATED_WARNINGS
    assert all(s.rstrip(".") in w for s, w in zip(sentences, warnings, strict=False))


def other_workspace_posts(factory, same_user: bool) -> UUID:
    """A Ready sample-posts document with line vectors in a workspace that is not the local
    one, owned by the local user or by another."""
    if not same_user:
        setup_source(factory, content=POST, title="Posts", kind="sample_posts", other=True)
        with factory() as session:
            document_id = session.scalar(
                select(KnowledgeDocument.id).where(KnowledgeDocument.title == "Posts")
            )
    else:
        with factory.begin() as session:
            workspace = Workspace(name="Second", user_id=LOCAL_USER_ID)
            session.add(workspace)
            session.flush()
            document = KnowledgeDocument(
                user_id=LOCAL_USER_ID,
                workspace_id=workspace.id,
                title="Posts",
                source_type="text",
                source_text=POST,
                status="Ready",
                embedding_profile=profile_key(),
                kind="sample_posts",
            )
            session.add(document)
            session.flush()
            document_id = document.id
    with patch("app.restatement.embed_texts", side_effect=embed_as({})):
        assert ensure_line_vectors(document_id) == 3
    return document_id


@pytest.mark.parametrize("same_user", [True, False])
def test_another_workspaces_lines_are_never_compared(service_api, same_user):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory, content="Rosemary grows in the garden.", title="Garden")
    other_workspace_posts(factory, same_user)
    draft_with(generation, "Success alone does not make a mentor.")
    with patch("app.restatement.embed_texts", side_effect=embed_as({})) as embed:
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == []
    embed.assert_not_called()


def test_a_second_line_job_for_a_document_being_embedded_leaves_at_once():
    with (
        patch("app.worker.embedding_lock", return_value=nullcontext(False)),
        patch("app.worker.ensure_line_vectors") as ensure,
    ):
        embed_sample_lines("00000000-0000-0000-0000-000000000001")
    ensure.assert_not_called()
    with (
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
        patch("app.worker.ensure_line_vectors", return_value=0) as ensure,
    ):
        embed_sample_lines("00000000-0000-0000-0000-000000000001")
    ensure.assert_called_once_with(UUID("00000000-0000-0000-0000-000000000001"))
