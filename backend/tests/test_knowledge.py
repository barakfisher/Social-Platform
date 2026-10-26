from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.chunking import chunk_text, normalize_text, token_count
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument, User, Workspace
from app.worker import process_text


def test_unicode_chunk_boundaries_overlap_and_coverage():
    source = normalize_text("כותרת\r\n\r\nEnglish ועברית עם אימוג׳י 🌱. " * 250)
    chunks = chunk_text(source)
    assert len(chunks) > 2
    assert chunks[0]["source_location"]["char_start"] == 0
    assert chunks[-1]["source_location"]["char_end"] == len(source)
    previous_end = 0
    for chunk in chunks:
        start, end = chunk["source_location"]["char_start"], chunk["source_location"]["char_end"]
        assert start <= previous_end
        assert chunk["content"] == source[start:end]
        assert chunk["token_count"] == token_count(chunk["content"]) <= 800
        assert "�" not in chunk["content"]
        previous_end = end
    assert token_count(chunk_text("<|endoftext|>")[0]["content"]) > 0
    with pytest.raises(ValueError):
        chunk_text("   ")


def job_for(factory, document_id):
    with factory() as session:
        return str(
            session.scalar(
                select(IngestionJob.id).where(IngestionJob.document_id == UUID(document_id))
            )
        )


def test_submit_prepare_deduplicate_and_delete(api):
    client, factory, dispatch = api
    payload = {"title": "ידע", "text": "  שלום\r\nEnglish  "}
    response = client.post("/knowledge/text", json=payload)
    assert response.status_code == 202
    result = response.json()
    assert result["stage"] == "pending"
    assert "text" not in result
    job_id = job_for(factory, result["id"])
    dispatch.assert_called_once_with(args=[job_id], task_id=job_id)
    # Normalized duplicate content returns the original, independent of title.
    duplicate = client.post("/knowledge/text", json={"title": "Another", "text": "שלום\nEnglish"})
    assert duplicate.json()["id"] == result["id"]
    assert duplicate.json()["duplicate"] is True
    assert dispatch.call_count == 1
    process_text(job_id)
    process_text(job_id)
    prepared = client.get(result["status_url"]).json()
    assert prepared["text"] == "שלום\nEnglish"
    assert prepared["stage"] == "text_prepared"
    assert prepared["status"] == "Processing"  # Not eligible for retrieval without embeddings.
    assert prepared["chunk_count"] == 1
    with factory() as session:
        assert session.get(IngestionJob, UUID(job_id)).attempts == 1
    assert client.post(f"{result['status_url']}/retry").status_code == 409
    assert client.delete(result["status_url"]).status_code == 200
    process_text(job_id)  # A queued delivery cannot recreate deleted content.
    assert client.get(result["status_url"]).status_code == 404
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeChunk)) == 0
        assert session.get(IngestionJob, UUID(job_id)) is None


def test_dispatch_failure_and_retry_preserve_source(api):
    client, factory, dispatch = api
    dispatch.side_effect = ConnectionError("broker down")
    result = client.post("/knowledge/text", json={"title": "source", "text": "durable text"}).json()
    assert result["status"] == "Failed"
    assert result["error_code"] == "dispatch_failed"
    assert client.get(result["status_url"]).json()["text"] == "durable text"
    dispatch.side_effect = None
    assert client.post(f"{result['status_url']}/retry").status_code == 202
    process_text(job_for(factory, result["id"]))
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"


def test_permanent_failure_is_recorded_and_can_retry(api):
    client, factory, _ = api
    result = client.post("/knowledge/text", json={"title": "source", "text": "valid source"}).json()
    job_id = job_for(factory, result["id"])
    with patch("app.worker.chunk_text", side_effect=ValueError("invalid source")):
        process_text.apply(args=[job_id], throw=False)
    assert client.get(result["status_url"]).json()["error_code"] == "processing_failed"
    assert client.post(f"{result['status_url']}/retry").status_code == 202
    process_text(job_id)
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": " ", "text": "value"},
        {"title": "title", "text": "   "},
        {"title": "title", "text": "x" * 100001},
        {"title": "title", "text": "nul\x00byte"},
        {"title": "title", "text": "source", "workspace_id": str(uuid4())},
    ],
)
def test_invalid_sources(api, payload):
    client, _, dispatch = api
    assert client.post("/knowledge/text", json=payload).status_code == 422
    dispatch.assert_not_called()


def test_other_workspace_cannot_be_read_retried_or_deleted(api):
    client, factory, dispatch = api
    with factory.begin() as session:
        user = User(name="Other")
        session.add(user)
        session.flush()
        workspace = Workspace(name="Other", user_id=user.id)
        session.add(workspace)
        session.flush()
        document = KnowledgeDocument(
            user_id=user.id,
            workspace_id=workspace.id,
            title="Private",
            source_type="text",
            source_text="private",
        )
        session.add(document)
        session.flush()
        path = f"/knowledge/{document.id}"
    assert client.get("/knowledge").json()["total"] == 0
    assert client.get(path).status_code == 404
    assert client.post(path + "/retry").status_code == 404
    assert client.delete(path).status_code == 404
    dispatch.assert_not_called()


def test_pending_jobs_can_be_recovered_after_broker_loss(api):
    from datetime import UTC, datetime, timedelta

    from app.reconcile import requeue_pending

    client, factory, dispatch = api
    result = client.post("/knowledge/text", json={"title": "Recovery", "text": "Recover me"}).json()
    job_id = job_for(factory, result["id"])
    with factory.begin() as session:
        job = session.get(IngestionJob, UUID(job_id))
        job.updated_at = datetime.now(UTC) - timedelta(minutes=3)
    dispatch.reset_mock()
    with patch("app.reconcile.SessionLocal", factory):
        assert requeue_pending() == 1
    dispatch.assert_called_once_with(args=[job_id], task_id=job_id)
    process_text(job_id)
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"
