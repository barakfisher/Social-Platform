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


def two_concepts(factory, settings, ahead=None) -> tuple[str, str]:  # noqa: F811
    # The run that found the miss: one document's chunks all rank above the second
    # concept's best chunk, which is still inside the distance limit.
    count, cap = settings.generation_retrieval_count, settings.generation_chunks_per_document
    assert cap < count, "the cap must leave room for a second document"
    ahead = ahead or count + 2
    limit = settings.generation_max_distance
    coaching = add_document(factory, "Coaching", [limit * 0.9 * i / ahead for i in range(ahead)])
    mentoring = add_document(factory, "Mentoring", [limit * 0.95])
    return coaching, mentoring


def test_one_document_no_longer_fills_every_slot(service_api, settings):  # noqa: F811
    _, factory, _, _ = service_api
    coaching, mentoring = two_concepts(factory, settings)
    # Before SP-25: nearest first only, and the second concept is missing.
    assert {s["document_id"] for s in search(factory, None)} == {coaching}
    found = search(factory, settings.generation_chunks_per_document)
    assert len(found) == settings.generation_retrieval_count
    # The cap freed slots; with no third document, they went back to the first one.
    assert [s["document_id"] for s in found].count(coaching) == len(found) - 1
    # Each document's best chunk comes first, so a tight budget trims repeats first.
    assert [s["document_id"] for s in found[:2]] == [coaching, mentoring]


def test_a_second_document_is_found_behind_any_number_of_nearer_chunks(service_api, settings):  # noqa: F811
    # No candidate-pool ceiling: the cap is applied per document in SQL.
    _, factory, _, _ = service_api
    _, mentoring = two_concepts(factory, settings, ahead=settings.generation_retrieval_count * 8)
    found = search(factory, settings.generation_chunks_per_document)
    assert mentoring in {s["document_id"] for s in found}


def test_a_single_relevant_document_still_fills_every_slot(service_api, settings):  # noqa: F811
    _, factory, _, _ = service_api
    limit, count = settings.generation_max_distance, settings.generation_retrieval_count
    only = add_document(factory, "Only", [limit * 0.9 * i / (count + 3) for i in range(count + 3)])
    add_document(factory, "Far", [min(limit + 0.2, 1.9)])
    found = search(factory, settings.generation_chunks_per_document)
    assert [s["document_id"] for s in found] == [only] * count
    # Same chunks as before, nearest first.
    assert [s["chunk_id"] for s in found] == [s["chunk_id"] for s in search(factory, None)]


def test_a_weaker_document_within_the_limit_takes_the_main_documents_extra_slots(
    service_api,  # noqa: F811
    settings,  # noqa: F811
):
    # The designed trade-off: a single-concept topic keeps the cap's worth of its main
    # document and gives the remaining slots to other documents inside the limit.
    _, factory, _, _ = service_api
    count, cap = settings.generation_retrieval_count, settings.generation_chunks_per_document
    limit = settings.generation_max_distance
    main = add_document(factory, "Main", [limit * 0.5 * i / (count + 1) for i in range(count + 1)])
    weak = add_document(factory, "Weak", [limit * 0.99] * (count - cap))
    found = [s["document_id"] for s in search(factory, cap)]
    assert found.count(main) == cap and found.count(weak) == count - cap
    assert found[:2] == [main, weak]


def test_nothing_within_the_limit_is_still_insufficient_context(service_api, settings):  # noqa: F811
    client, factory, embeddings, generation = service_api
    setup_brand(factory)
    add_document(factory, "Far", [min(settings.generation_max_distance + 0.2, 1.9)] * 3)
    response = client.post("/generation", json=payload())
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "insufficient_context"
    # Retrieval ran and found nothing: the empty result is not an earlier exit.
    embeddings.assert_called_once()
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


def test_both_retrieval_calls_use_the_per_document_cap(service_api, settings):  # noqa: F811
    # The original query and the translated fallback query.
    client, factory, _, _ = service_api
    setup_brand(factory)
    add_document(factory, "Garden", [0.1])
    with factory() as session:
        sources = search_context(
            session,
            [1.0, 0.0, 0.0],
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            limit=settings.generation_retrieval_count,
        )
    translated = ("query", {"usage": {"cost_usd": 0.0}, "cost_usd": 0.0}, 0.0)
    with (
        patch("app.generation.search_context", side_effect=[[], sources]) as retrieval,
        patch("app.generation.translate_query", return_value=translated),
    ):
        assert client.post("/generation", json=payload()).status_code == 200
    assert retrieval.call_count == 2
    cap = settings.generation_chunks_per_document
    assert all(call.kwargs["per_document"] == cap for call in retrieval.call_args_list)


def candidate(document: str, distance: float) -> dict:
    return {"document_id": document, "distance": distance, "chunk_id": f"{document}{distance}"}


def test_spread_fills_from_the_nearest_and_puts_each_documents_best_first():
    capped = [candidate("a", 0.1), candidate("a", 0.2), candidate("b", 0.4)]
    nearest = [candidate("a", 0.1), candidate("a", 0.2), candidate("a", 0.3), candidate("b", 0.4)]
    spread = spread_across_documents(capped, nearest, count=4)
    assert [c["chunk_id"] for c in spread] == ["a0.1", "b0.4", "a0.2", "a0.3"]
    assert len(spread_across_documents(capped, nearest, count=3)) == 3
