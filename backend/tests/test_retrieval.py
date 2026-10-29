"""Retrieval spread across documents (SP-25): one document must not fill every slot."""

import json
import math
from unittest.mock import patch

from app.config import get_settings
from app.embeddings import profile_key
from app.grounding import prompt_tokens
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import KnowledgeChunk, KnowledgeDocument
from app.retrieval import search_context, spread_across_documents
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    payload,
    service_api,
    settings,
    setup_brand,
)


def at_distance(distance: float) -> list[float]:
    """A 3-d unit vector whose cosine distance from [1, 0, 0] is exactly distance."""
    similarity = 1 - distance
    return [similarity, math.sqrt(1 - similarity**2), 0.0]


def add_document(factory, title: str, distances: list[float]) -> str:
    with factory.begin() as session:
        seed_local_scope(session)
        document = KnowledgeDocument(
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            title=title,
            source_type="text",
            source_text=title,
            status="Ready",
            embedding_profile=profile_key(),
        )
        session.add(document)
        session.flush()
        for order, distance in enumerate(distances):
            session.add(
                KnowledgeChunk(
                    user_id=LOCAL_USER_ID,
                    workspace_id=LOCAL_WORKSPACE_ID,
                    document_id=document.id,
                    chunk_order=order,
                    content=f"{title} chunk {order}",
                    token_count=5,
                    embedding=at_distance(distance),
                    embedding_dimensions=3,
                    embedding_model=get_settings().embedding_model,
                    embedding_profile=profile_key(),
                    source_location={"char_start": 0, "char_end": 10},
                )
            )
        return str(document.id)


def search(factory, per_document):
    config = get_settings()
    with factory() as session:
        return search_context(
            session,
            [1.0, 0.0, 0.0],
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            limit=config.generation_retrieval_count,
            max_distance=config.generation_max_distance,
            per_document=per_document,
        )


def two_concepts(factory, settings) -> tuple[str, str]:  # noqa: F811
    # The run that found the miss: one document's chunks all rank above the second
    # concept's best chunk, which is still inside the distance limit.
    limit = settings.generation_max_distance
    near = [limit * step / 10 for step in range(1, settings.generation_retrieval_count + 3)]
    coaching = add_document(factory, "Coaching", near)
    mentoring = add_document(factory, "Mentoring", [limit * 0.95])
    return coaching, mentoring


def test_one_document_no_longer_fills_every_slot(service_api, settings):  # noqa: F811
    _, factory, _, _ = service_api
    coaching, mentoring = two_concepts(factory, settings)
    # Before SP-25: nearest first only, and the second concept is missing.
    assert {s["document_id"] for s in search(factory, None)} == {coaching}
    found = search(factory, settings.generation_chunks_per_document)
    assert len(found) == settings.generation_retrieval_count
    assert {s["document_id"] for s in found} == {coaching, mentoring}
    # The cap freed slots; with no third document, they go back to the first one.
    assert sum(s["document_id"] == mentoring for s in found) == 1
    # Each document's best chunk comes first, so a tight budget trims repeats first.
    assert [s["document_id"] for s in found[:2]] == [coaching, mentoring]


def test_a_single_relevant_document_still_fills_every_slot(service_api, settings):  # noqa: F811
    _, factory, _, _ = service_api
    limit = settings.generation_max_distance
    only = add_document(factory, "Only", [limit * step / 10 for step in range(1, 9)])
    add_document(factory, "Far", [min(limit + 0.2, 1.9)])
    found = search(factory, settings.generation_chunks_per_document)
    assert [s["document_id"] for s in found] == [only] * settings.generation_retrieval_count
    # Same chunks as before, nearest first.
    assert [s["chunk_id"] for s in found] == [s["chunk_id"] for s in search(factory, None)]


def test_nothing_within_the_limit_is_still_insufficient_context(service_api, settings):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    add_document(factory, "Far", [min(settings.generation_max_distance + 0.2, 1.9)] * 3)
    response = client.post("/generation", json=payload())
    assert response.json()["error"]["message"] == "insufficient_context"
    generation.assert_not_called()


def test_writer_receives_both_concepts_within_a_tight_context_budget(service_api, settings):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    two_concepts(factory, settings)
    # Room for exactly two chunks: nearest-first order would send two coaching chunks.
    found = search(factory, settings.generation_chunks_per_document)
    settings.generation_context_budget = prompt_tokens(json.dumps(found[:2], ensure_ascii=False))
    with patch("app.generation.translate_query", return_value=None):
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    sent = generation.call_args.args[1]
    assert "Mentoring chunk 0" in sent and "Coaching chunk 0" in sent
    assert "Coaching chunk 1" not in sent


def test_spread_fills_held_slots_and_keeps_distance_order_within_documents():
    candidates = [
        {"document_id": "a", "distance": 0.1, "chunk_id": "a1"},
        {"document_id": "a", "distance": 0.2, "chunk_id": "a2"},
        {"document_id": "a", "distance": 0.3, "chunk_id": "a3"},
        {"document_id": "b", "distance": 0.4, "chunk_id": "b1"},
    ]
    spread = spread_across_documents(candidates, count=4, per_document=2)
    assert [c["chunk_id"] for c in spread] == ["a1", "b1", "a2", "a3"]
    assert len(spread_across_documents(candidates, count=2, per_document=1)) == 2
