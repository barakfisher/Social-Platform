from contextlib import nullcontext
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from test_knowledge import job_for

from app.config import get_settings
from app.embeddings import EmbeddingError, TransientEmbeddingError, embed_texts, profile_key
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.worker import embed_document, process_text

RealClient = httpx.Client


@pytest.fixture(autouse=True)
def embedding_settings():
    settings = get_settings()
    original = settings.model_copy(deep=True)
    settings.embedding_api_key = SecretStr("dummy-test-key")
    settings.embedding_model = "test/embedding"
    settings.embedding_dimensions = 3
    settings.embedding_batch_size = 2
    yield settings
    for field in type(settings).model_fields:
        setattr(settings, field, getattr(original, field))


def response_for(request, vector=None):
    import json

    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "model": get_settings().embedding_model,
            "data": [
                {"index": i, "embedding": vector or [1.0, 0.0, 0.0]}
                for i in reversed(range(len(body["input"])))
            ],
        },
    )


@pytest.fixture
def provider():
    def install(handler=response_for):
        return patch(
            "app.embeddings.httpx.Client",
            side_effect=lambda **kwargs: RealClient(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )

    return install


def test_validates_and_orders_provider_vectors(provider):
    with provider():
        assert embed_texts(["English", "עברית"]) == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]


@pytest.mark.parametrize("vector", [[1, 0], [0, 0, 0], [True, 0, 0], ["one", 0, 0], [1e100, 0, 0]])
def test_rejects_invalid_vectors(provider, vector):
    with (
        provider(lambda request: response_for(request, vector)),
        pytest.raises(EmbeddingError) as error,
    ):
        embed_texts(["source"])
    assert error.value.code == "embedding_invalid_response"


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "wrong", "data": [{"index": 0, "embedding": [1, 0, 0]}]},
        {"model": "test/embedding", "data": []},
        {"model": "test/embedding", "data": [{"index": 1, "embedding": [1, 0, 0]}]},
        {"model": "test/embedding", "data": "invalid"},
    ],
)
def test_rejects_malformed_batches(provider, payload):
    with provider(lambda request: httpx.Response(200, json=payload)), pytest.raises(EmbeddingError):
        embed_texts(["source"])


@pytest.mark.parametrize(
    "status,code", [(429, "embedding_rate_limited"), (503, "embedding_unavailable")]
)
def test_transient_failures_are_retryable_without_leaking_provider_body(provider, status, code):
    with provider(lambda request: httpx.Response(status, text="sensitive provider body")):
        with pytest.raises(TransientEmbeddingError) as error:
            embed_texts(["source"])
    assert str(error.value) == code


def test_missing_key_is_explicit(embedding_settings):
    embedding_settings.embedding_api_key = SecretStr("")
    with pytest.raises(EmbeddingError, match="embedding_not_configured"):
        embed_texts(["source"])


def prepare(client, factory, text="English ועברית"):
    result = client.post("/knowledge/text", json={"title": "Embedding test", "text": text}).json()
    process_text(job_for(factory, result["id"]))
    response = client.post(result["status_url"] + "/embed")
    assert response.status_code == 202
    with factory() as session:
        job_id = str(
            session.scalar(
                select(IngestionJob.id).where(
                    IngestionJob.document_id == UUID(result["id"]), IngestionJob.kind == "embedding"
                )
            )
        )
    return result, job_id


def test_embedding_ready_gating_idempotency_and_matching_search(api, provider):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        result, job_id = prepare(client, factory)
        assert client.get(result["status_url"]).json()["status"] == "Processing"
        with provider():
            embed_document(job_id)
            embed_document(job_id)
            found = client.post("/knowledge/search", json={"query": "עברית"}).json()
        ready = client.get(result["status_url"]).json()
        assert ready["status"] == "Ready"
        assert ready["embedded_chunk_count"] == ready["chunk_count"] == 1
        assert found["items"][0]["document_id"] == result["id"]
        with factory() as session:
            assert session.get(IngestionJob, UUID(job_id)).attempts == 1
        get_settings().embedding_revision = "2"
        with provider():
            assert (
                client.post("/knowledge/search", json={"query": "same query"}).json()["items"] == []
            )
        assert client.get(result["status_url"]).json()["stage"] == "text_prepared"


def test_partial_batches_resume_without_repeating_completed_vectors(
    api, provider, embedding_settings
):
    client, factory, _ = api
    embedding_settings.embedding_batch_size = 1
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(429)
        return response_for(request)

    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        result, job_id = prepare(client, factory, ("Long source. מקור בעברית.\n\n" * 200))
        with provider(handler), pytest.raises(TransientEmbeddingError):
            embed_document(job_id)
        with factory() as session:
            count = session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == UUID(result["id"]),
                    KnowledgeChunk.embedding_profile == profile_key(),
                )
            )
            assert count == 1
        with provider(handler):
            embed_document(job_id)
        ready = client.get(result["status_url"]).json()
        assert ready["status"] == "Ready"
        assert len(calls) == ready["chunk_count"] + 1  # Only the failed batch was repeated.


def test_invalid_response_records_failure_and_no_vectors(api, provider):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        result, job_id = prepare(client, factory)
        with provider(lambda request: response_for(request, [1, 0])):
            embed_document.apply(args=[job_id], throw=False)
    failed = client.get(result["status_url"]).json()
    assert failed["status"] == "Failed"
    assert failed["stage"] == "embedding_failed"
    assert failed["error_code"] == "embedding_invalid_response"
    assert failed["embedded_chunk_count"] == 0


def test_deletion_during_provider_call_cannot_recreate_source(api, provider):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        result, job_id = prepare(client, factory)

        def handler(request):
            assert client.delete(result["status_url"]).status_code == 200
            return response_for(request)

        with provider(handler):
            embed_document(job_id)
    assert client.get(result["status_url"]).status_code == 404
    with factory() as session:
        assert session.get(KnowledgeDocument, UUID(result["id"])) is None


def test_no_key_exposes_configuration_without_secrets(api, embedding_settings):
    client, factory, _ = api
    configuration = client.get("/knowledge/configuration")
    assert configuration.json()["configured"] is True
    assert "dummy-test-key" not in configuration.text
    embedding_settings.embedding_api_key = SecretStr("")
    result = client.post("/knowledge/text", json={"title": "Saved", "text": "knowledge"}).json()
    process_text(job_for(factory, result["id"]))
    assert client.post(result["status_url"] + "/embed").status_code == 503
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"


def test_job_lock_excludes_duplicate_worker_and_releases():
    import os
    from uuid import uuid4

    from app.embeddings import embedding_lock

    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL advisory lock verification")
    job_id = str(uuid4())
    with embedding_lock(job_id) as first:
        assert first is True
        with embedding_lock(job_id) as duplicate:
            assert duplicate is False
    with embedding_lock(job_id) as after_release:
        assert after_release is True


def test_retrieval_excludes_other_workspace_and_wrong_profile(api, provider):
    from app.models import User, Workspace

    client, factory, _ = api
    with factory.begin() as session:
        user = User(name="Other tenant")
        session.add(user)
        session.flush()
        workspace = Workspace(name="Private", user_id=user.id)
        session.add(workspace)
        session.flush()
        document = KnowledgeDocument(
            user_id=user.id,
            workspace_id=workspace.id,
            title="Private",
            source_type="text",
            status="Ready",
            embedding_profile=profile_key(),
        )
        session.add(document)
        session.flush()
        session.add(
            KnowledgeChunk(
                user_id=user.id,
                workspace_id=workspace.id,
                document_id=document.id,
                chunk_order=0,
                content="private",
                token_count=1,
                embedding=[1, 0, 0],
                embedding_model=get_settings().embedding_model,
                embedding_dimensions=3,
                embedding_profile=profile_key(),
            )
        )
    with provider():
        result = client.post("/knowledge/search", json={"query": "private"})
    assert result.status_code == 200
    assert result.json()["items"] == []


def test_celery_retries_transient_provider_failure_and_persists_success(api):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        item, job_id = prepare(client, factory)
        with patch(
            "app.worker.embed_texts",
            side_effect=[
                TransientEmbeddingError("embedding_rate_limited"),
                [[1.0, 0.0, 0.0]],
            ],
        ) as provider:
            result = embed_document.apply(args=[job_id], throw=False)
        assert result.successful()
        assert provider.call_count == 2
    assert client.get(item["status_url"]).json()["status"] == "Ready"
    with factory() as session:
        assert session.get(IngestionJob, UUID(job_id)).attempts == 2


def test_celery_does_not_retry_permanent_provider_failure(api):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
    ):
        item, job_id = prepare(client, factory)
        with patch(
            "app.worker.embed_texts", side_effect=EmbeddingError("embedding_authentication_failed")
        ) as provider:
            result = embed_document.apply(args=[job_id], throw=False)
        assert result.failed()
        assert provider.call_count == 1
    response = client.get(item["status_url"]).json()
    assert response["status"] == "Failed"
    assert response["error_code"] == "embedding_authentication_failed"


def test_openrouter_accepts_verified_upstream_openai_model_alias(provider, embedding_settings):
    embedding_settings.embedding_model = "openai/text-embedding-3-small"

    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-small",
                "data": [{"index": 0, "embedding": [1, 0, 0]}],
            },
        )

    with provider(handler):
        assert embed_texts(["source"]) == [[1, 0, 0]]
    embedding_settings.embedding_base_url = "https://another-provider.example/v1"
    with provider(handler), pytest.raises(EmbeddingError, match="embedding_invalid_response"):
        embed_texts(["source"])


def test_openrouter_alias_does_not_accept_different_openai_model(provider, embedding_settings):
    embedding_settings.embedding_model = "openai/text-embedding-3-small"
    with (
        provider(
            lambda request: httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-large",
                    "data": [{"index": 0, "embedding": [1, 0, 0]}],
                },
            )
        ),
        pytest.raises(EmbeddingError),
    ):
        embed_texts(["source"])
