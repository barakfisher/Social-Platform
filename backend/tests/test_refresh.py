from contextlib import nullcontext
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.web_fetch import FetchError
from app.worker import embed_document, process_text
from tests.test_embeddings import embedding_settings, provider  # noqa: F401

PAGE = b"""<html><head><title>Garden hours</title></head><body><article><h1>Garden hours</h1>
<p>The community garden is open every day from eight in the morning until seven.</p>
</article></body></html>"""
NEW_PAGE = b"""<html><head><title>Garden hours</title></head><body><article><h1>Garden hours</h1>
<p>From November the community garden opens at nine and closes at five every day.</p>
</article></body></html>"""


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "source_storage_dir", str(tmp_path / "sources"))
    return tmp_path / "sources"


def stored_files(directory):
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def jobs(factory, document_id, kind="text_ingestion"):
    with factory() as session:
        return [
            str(job_id)
            for job_id in session.scalars(
                select(IngestionJob.id)
                .where(IngestionJob.document_id == UUID(document_id), IngestionJob.kind == kind)
                .order_by(IngestionJob.created_at)
            )
        ]


def staging_of(factory, document_id):
    with factory() as session:
        return session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.replaces_id == UUID(document_id))
        )


def chunk_ids(factory, document_id):
    with factory() as session:
        return set(
            session.scalars(
                select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == UUID(document_id))
            )
        )


def add_page(client, factory, page=PAGE):
    result = client.post("/knowledge/url", json={"url": "https://garden.example/hours"}).json()
    with patch("app.worker.fetch_page", return_value=page):
        process_text(jobs(factory, result["id"])[0])
    return result


def run_staging(factory, document_id, page):
    staging = staging_of(factory, document_id)
    with patch("app.worker.fetch_page", return_value=page):
        process_text(jobs(factory, str(staging.id))[0])
    return staging


def test_unchanged_page_only_updates_the_load_time(api, private_dir):
    client, factory, dispatch = api
    result = add_page(client, factory)
    before = client.get(result["status_url"]).json()
    assert before["fetched_at"] and before["refresh"] is None
    old_chunks = chunk_ids(factory, result["id"])
    [page_copy] = stored_files(private_dir)

    response = client.post(f"{result['status_url']}/refresh")
    assert response.status_code == 202
    assert response.json()["refresh"] == {
        "status": "Pending",
        "stage": "pending",
        "error_code": None,
    }
    # The staging copy is internal: not listed, not addressable, not counted.
    staging = staging_of(factory, result["id"])
    listed = client.get("/knowledge").json()
    assert listed["total"] == 1 and [i["id"] for i in listed["items"]] == [result["id"]]
    assert client.get(f"/knowledge/{staging.id}").status_code == 404
    # A second click while it runs starts nothing new.
    assert client.post(f"{result['status_url']}/refresh").status_code == 202
    assert dispatch.call_count == 2

    run_staging(factory, result["id"], PAGE)
    after = client.get(result["status_url"]).json()
    assert after["refresh"] is None and after["refresh_result"] == "unchanged"
    assert after["fetched_at"] > before["fetched_at"]
    assert chunk_ids(factory, result["id"]) == old_chunks
    assert stored_files(private_dir) == [page_copy]
    assert staging_of(factory, result["id"]) is None


def test_changed_page_that_is_not_searchable_yet_is_replaced_at_once(api, private_dir):
    client, factory, dispatch = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    [old_copy] = stored_files(private_dir)
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    after = client.get(result["status_url"]).json()
    assert after["refresh_result"] == "updated" and after["refresh"] is None
    assert "opens at nine" in after["text"]
    assert after["stage"] == "text_prepared"
    assert chunk_ids(factory, result["id"]).isdisjoint(old_chunks)
    [new_copy] = stored_files(private_dir)
    assert new_copy != old_copy
    assert dispatch.call_count == 2  # No embedding job: the page was not searchable.


def test_searchable_page_stays_in_use_until_the_new_version_is_embedded(
    api,
    private_dir,
    provider,  # noqa: F811
):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async") as embed_dispatch,
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
        provider(),
    ):
        result = add_page(client, factory)
        assert client.post(f"{result['status_url']}/embed").status_code == 202
        embed_document(jobs(factory, result["id"], "embedding")[0])
        assert client.get(result["status_url"]).json()["status"] == "Ready"
        old_chunks = chunk_ids(factory, result["id"])
        found = client.post("/knowledge/search", json={"query": "garden"}).json()["items"]
        assert {item["document_id"] for item in found} == {result["id"]}

        client.post(f"{result['status_url']}/refresh")
        staging = run_staging(factory, result["id"], NEW_PAGE)
        [embed_job] = jobs(factory, str(staging.id), "embedding")
        embed_dispatch.assert_called_with(args=[embed_job], task_id=embed_job)
        # Old version still searchable; the staging copy is never a search result.
        during = client.get(result["status_url"]).json()
        assert during["status"] == "Ready" and during["refresh"]["stage"] == "embedding_pending"
        assert chunk_ids(factory, result["id"]) == old_chunks
        found = client.post("/knowledge/search", json={"query": "garden"}).json()["items"]
        assert {item["document_id"] for item in found} == {result["id"]}
        assert client.post(f"{result['status_url']}/embed").status_code == 409

        embed_document(embed_job)
        after = client.get(result["status_url"]).json()
        assert after["status"] == "Ready" and after["refresh_result"] == "updated"
        assert after["embedded_chunk_count"] == after["chunk_count"] > 0
        assert "opens at nine" in after["text"]
        assert chunk_ids(factory, result["id"]).isdisjoint(old_chunks)
        assert staging_of(factory, result["id"]) is None
        assert len(stored_files(private_dir)) == 1


def test_failed_refresh_keeps_the_old_version_and_can_be_tried_again(api, private_dir):
    client, factory, dispatch = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    client.post(f"{result['status_url']}/refresh")
    staging = staging_of(factory, result["id"])
    with patch("app.worker.fetch_page", side_effect=FetchError("url_timeout")):
        process_text(jobs(factory, str(staging.id))[0])
    failed = client.get(result["status_url"]).json()
    assert failed["refresh"] == {"status": "Failed", "stage": "failed", "error_code": "url_timeout"}
    assert failed["stage"] == "text_prepared" and failed["error_code"] is None
    assert chunk_ids(factory, result["id"]) == old_chunks

    assert client.post(f"{result['status_url']}/refresh").status_code == 202
    assert staging_of(factory, result["id"]).id != staging.id
    run_staging(factory, result["id"], NEW_PAGE)
    assert client.get(result["status_url"]).json()["refresh_result"] == "updated"


def test_deleting_during_a_refresh_removes_the_staging_copy_and_its_page(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    client.post(f"{result['status_url']}/refresh")
    staging = staging_of(factory, result["id"])

    def fetch_then_delete(url):
        assert client.delete(result["status_url"]).status_code == 200
        return NEW_PAGE

    with patch("app.worker.fetch_page", side_effect=fetch_then_delete):
        process_text(jobs(factory, str(staging.id))[0])
    assert stored_files(private_dir) == []
    with factory() as session:
        assert session.scalar(select(KnowledgeDocument.id)) is None


def test_refresh_is_refused_where_it_cannot_run(api, private_dir):
    client, factory, _ = api
    pasted = client.post("/knowledge/text", json={"title": "t", "text": "pasted"}).json()
    assert client.post(f"{pasted['status_url']}/refresh").json()["error"]["message"] == (
        "refresh_not_supported"
    )
    pending = client.post("/knowledge/url", json={"url": "https://garden.example/x"}).json()
    response = client.post(f"{pending['status_url']}/refresh")
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "refresh_not_ready"

    result = add_page(client, factory)
    with factory.begin() as session:
        session.get(KnowledgeDocument, UUID(result["id"])).status = "Ready"
    with patch("app.knowledge.configured", return_value=False):
        response = client.post(f"{result['status_url']}/refresh")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "embedding_not_configured"
    assert staging_of(factory, result["id"]) is None
