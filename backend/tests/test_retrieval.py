"""The writer reads every chunk within the distance limit, up to the context budget.

SP-25 spread retrieval across documents; since 2026-10-31 relevance alone decides what the
writer reads, and GENERATION_CONTEXT_BUDGET is only a safety cap (docs/implementation.md).
"""

import json
import math
from unittest.mock import patch

from app.config import get_settings
from app.embeddings import profile_key
from app.generation import SYSTEM
from app.grounding import prompt_tokens
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import KnowledgeChunk, KnowledgeDocument
from app.retrieval import documents_first, relevant_context
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    payload,
    service_api,
    settings,
    setup_brand,
)

# Several hundred o200k tokens of Hebrew, like a real chunk.
HEBREW_CHUNK = "מנטורינג הוא תהליך שבו אדם מנוסה מלווה אדם אחר בדרכו המקצועית. " * 40


def at_distance(distance: float) -> list[float]:
    """A 3-d unit vector whose cosine distance from [1, 0, 0] is exactly distance."""
    similarity = 1 - distance
    return [similarity, math.sqrt(1 - similarity**2), 0.0]


def add_document(factory, title: str, distances: list[float], content: str = "") -> str:
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
                    content=f"{title} chunk {order}. {content}",
                    token_count=5,
                    embedding=at_distance(distance),
                    embedding_dimensions=3,
                    embedding_model=get_settings().embedding_model,
                    embedding_profile=profile_key(),
                    source_location={"char_start": 0, "char_end": 10},
                )
            )
        return str(document.id)


def search(factory):
    with factory() as session:
        return relevant_context(
            session,
            [1.0, 0.0, 0.0],
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            max_distance=get_settings().generation_max_distance,
        )


def spread(limit: float, count: int, share: float = 0.9) -> list[float]:
    """count distances evenly inside share of the limit, nearest first."""
    return [limit * share * i / count for i in range(count)]


def two_concepts(factory, settings, ahead: int) -> tuple[str, str]:  # noqa: F811
    # The run that found the SP-25 miss: one document's chunks all rank above the second
    # concept's best chunk, which is still inside the distance limit.
    limit = settings.generation_max_distance
    coaching = add_document(factory, "Coaching", spread(limit, ahead))
    mentoring = add_document(factory, "Mentoring", [limit * 0.95])
    return coaching, mentoring


def sent_sources(generation) -> list[dict]:
    return json.loads(generation.call_args.args[1])["sources"]


def test_every_chunk_within_the_limit_reaches_the_writer(service_api, settings):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    limit = settings.generation_max_distance
    # More chunks than the old fixed count of five, across two documents.
    main = add_document(factory, "Main", spread(limit, 12))
    weak = add_document(factory, "Weak", [limit * 0.99] * 4)
    add_document(factory, "Far", [min(limit + 0.2, 1.9)] * 3)
    response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    sent = [s["document_id"] for s in sent_sources(generation)]
    assert sent.count(main) == 12 and sent.count(weak) == 4
    assert len(sent) == 16


def test_a_second_document_is_found_behind_any_number_of_nearer_chunks(service_api, settings):  # noqa: F811
    _, factory, _, _ = service_api
    coaching, mentoring = two_concepts(factory, settings, ahead=40)
    found = [s["document_id"] for s in search(factory)]
    # Each document's best chunk first, so a tight budget trims repeats before documents.
    assert found[:2] == [coaching, mentoring]
    assert found.count(coaching) == 40


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
    two_concepts(factory, settings, ahead=6)
    # Room for exactly two chunks: nearest-first order would send two coaching chunks.
    found = search(factory)
    settings.generation_context_budget = prompt_tokens(json.dumps(found[:2], ensure_ascii=False))
    response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    sent = generation.call_args.args[1]
    assert "Mentoring chunk 0" in sent and "Coaching chunk 0" in sent
    assert "Coaching chunk 1" not in sent


def test_a_full_context_budget_is_the_only_ceiling(service_api, settings):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    limit = settings.generation_max_distance
    chunk = prompt_tokens(HEBREW_CHUNK)
    count = settings.generation_context_budget // chunk + 3
    add_document(factory, "Long", spread(limit, count), HEBREW_CHUNK)
    response = client.post("/generation", json=payload(language="he"))
    assert response.status_code == 200, response.text
    sent = sent_sources(generation)
    used = prompt_tokens(json.dumps(sent, ensure_ascii=False))
    # Filled to the budget, nearest first, and cut only at the end.
    assert settings.generation_context_budget - 2 * chunk < used
    assert used <= settings.generation_context_budget
    nearest = [s["chunk_id"] for s in search(factory)]
    assert [s["chunk_id"] for s in sent] == nearest[: len(sent)]


def test_writer_and_reviewer_prompts_admit_a_full_context_and_the_longest_draft(
    service_api,  # noqa: F811
    settings,  # noqa: F811
):
    # The prompt budget leaves room for each stage's own instructions, a full context, the
    # brand, the preferences and, for the reviewer, the longest draft twice (draft and
    # sentences). The writer may cite every source it received.
    client, factory, _, generation = service_api
    setup_brand(factory)
    limit = settings.generation_max_distance
    count = settings.generation_context_budget // prompt_tokens(HEBREW_CHUNK) + 3
    add_document(factory, "Long", spread(limit, count), HEBREW_CHUNK)
    longest = {"short": 600, "medium": 1200, "long": 2400}["long"]
    draft = ("טיוטה שמבוססת על המקורות שנשלחו לכותב. " * 100)[:longest].strip()

    def cite_everything(system, user, tokens, **kwargs):
        assert system == SYSTEM
        ids = [s["chunk_id"] for s in json.loads(user)["sources"]]
        return json.dumps({"content": draft, "source_ids": ids, "warnings": []}), {
            "model": "test/model",
            "usage": {"prompt_tokens": tokens, "completion_tokens": 900, "cost_usd": 0.01},
        }

    generation.side_effect = cite_everything
    body = payload(language="he", length="long", topic="מנטורינג " * 100)
    response = client.post("/generation", json=body)
    assert response.status_code == 200, response.text
    # "Check sources" on that draft: a reviewer prompt over the budget would still return 200,
    # marked unchecked, so only "checked" shows it fit.
    checked = client.post(f"/generation/{response.json()['id']}/review", json={})
    assert checked.status_code == 200, checked.text
    assert checked.json()["metadata"]["grounding_review"]["status"] == "checked"
    cited = response.json()["sources"]
    assert len(cited) == len(sent_sources(generation))
    assert prompt_tokens(json.dumps(cited, ensure_ascii=False)) > (
        settings.generation_context_budget * 0.9
    )


def test_both_retrieval_calls_use_the_distance_limit(service_api, settings):  # noqa: F811
    # The original query and the translated fallback query.
    client, factory, _, _ = service_api
    setup_brand(factory)
    add_document(factory, "Garden", [0.1])
    sources = search(factory)
    translated = ("query", {"usage": {"cost_usd": 0.0}, "cost_usd": 0.0}, 0.0)
    with (
        patch("app.generation.relevant_context", side_effect=[[], sources]) as retrieval,
        patch("app.generation.translate_query", return_value=translated),
    ):
        assert client.post("/generation", json=payload()).status_code == 200
    assert retrieval.call_count == 2
    limit = settings.generation_max_distance
    assert all(call.kwargs["max_distance"] == limit for call in retrieval.call_args_list)


def candidate(document: str, distance: float) -> dict:
    return {"document_id": document, "distance": distance, "chunk_id": f"{document}{distance}"}


def test_documents_first_puts_each_documents_best_chunk_first():
    chunks = [candidate("a", 0.1), candidate("a", 0.2), candidate("a", 0.3), candidate("b", 0.4)]
    ordered = documents_first(list(reversed(chunks)))
    assert [c["chunk_id"] for c in ordered] == ["a0.1", "b0.4", "a0.2", "a0.3"]
