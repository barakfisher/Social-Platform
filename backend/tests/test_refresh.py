from contextlib import nullcontext
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.refresh import changes
from app.web_fetch import FetchError
from app.worker import embed_document, process_text
from tests.test_embeddings import embedding_settings, provider  # noqa: F401

PAGE = b"""<html><head><title>Garden hours</title></head><body><article><h1>Garden hours</h1>
<p>The community garden is open every day from eight in the morning until seven.</p>
</article></body></html>"""
NEW_PAGE = b"""<html><head><title>Garden hours</title></head><body><article><h1>Garden hours</h1>
<p>From November the community garden opens at nine and closes at five every day.</p>
<p>A new seed library opened next to the tool shed for every member of the garden.</p>
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


def decide(client, result, action):
    return client.post(f"{result['status_url']}/refresh-decision", json={"action": action})


def text_of(client, result):
    return client.get(result["status_url"]).json()["text"]


def test_changes_compare_paragraphs_and_ignore_added_headings():
    old = "Intro\n\nOpen at eight.\n\n## Added 2026-10-29 / נוסף 2026-10-29\n\nOld news item."
    new = "Intro\n\n Open  at eight. \n\nFresh news item."
    assert changes(old, new) == (["Fresh news item."], ["Old news item."])
    assert changes(old, old) == ([], [])


def test_unchanged_page_only_updates_the_load_time(api, private_dir):
    client, factory, dispatch = api
    result = add_page(client, factory)
    before = client.get(result["status_url"]).json()
    assert before["fetched_at"] and before["refresh"] is None
    old_chunks = chunk_ids(factory, result["id"])
    [page_copy] = stored_files(private_dir)

    response = client.post(f"{result['status_url']}/refresh")
    assert response.status_code == 202
    assert response.json()["refresh"]["status"] == "Pending"
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


def test_changed_page_waits_for_a_choice_and_shows_the_changes(api, private_dir):
    client, factory, dispatch = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    waiting = client.get(result["status_url"]).json()
    assert waiting["refresh"]["stage"] == "awaiting_decision"
    assert waiting["refresh"]["added_count"] == 2 and waiting["refresh"]["removed_count"] == 1
    assert chunk_ids(factory, result["id"]) == old_chunks  # Nothing changes before the choice.
    shown = client.get(f"{result['status_url']}/refresh-changes").json()
    assert any("opens at nine" in p for p in shown["added"])
    assert any("eight in the morning" in p for p in shown["removed"])
    # Loading again while a choice is waiting starts nothing new.
    client.post(f"{result['status_url']}/refresh")
    assert dispatch.call_count == 2
    assert decide(client, result, "remove").status_code == 422


def test_replace_takes_the_new_version_at_once_when_not_searchable(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    [old_copy] = stored_files(private_dir)
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    after = decide(client, result, "replace").json()
    assert after["refresh_result"] == "replaced" and after["refresh"] is None
    assert after["stage"] == "text_prepared"
    text = text_of(client, result)
    assert "opens at nine" in text and "eight in the morning" not in text
    assert chunk_ids(factory, result["id"]).isdisjoint(old_chunks)
    [new_copy] = stored_files(private_dir)
    assert new_copy != old_copy
    assert decide(client, result, "replace").status_code == 409


def test_append_keeps_old_paragraphs_and_adds_only_new_ones_with_dates(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    old_text = text_of(client, result)
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    after = decide(client, result, "append").json()
    assert after["refresh_result"] == "appended"
    text = text_of(client, result)
    assert text.startswith(old_text + "\n\n## Added ")
    assert "eight in the morning" in text and "opens at nine" in text
    assert text.count("Garden hours") == old_text.count("Garden hours")  # Not added twice.
    assert old_chunks < chunk_ids(factory, result["id"])  # Existing chunks are kept.
    with factory() as session:
        chunks = session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == UUID(result["id"]))
            .order_by(KnowledgeChunk.chunk_order)
        ).all()
    assert [c.chunk_order for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        location = chunk.source_location
        assert text[location["char_start"] : location["char_end"]] == chunk.content
        assert location["added_on"]

    # The same page again: nothing new, and the appended section is not "removed".
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    assert client.get(result["status_url"]).json()["refresh"]["added_count"] == 0
    assert decide(client, result, "append").json()["refresh_result"] == "kept"
    assert text_of(client, result) == text


def test_keep_drops_the_new_version(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    [old_copy] = stored_files(private_dir)
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    after = decide(client, result, "keep").json()
    assert after["refresh_result"] == "kept" and after["refresh"] is None
    assert chunk_ids(factory, result["id"]) == old_chunks
    assert stored_files(private_dir) == [old_copy]
    assert staging_of(factory, result["id"]) is None


@pytest.mark.parametrize("action", ["replace", "append"])
def test_searchable_page_stays_in_use_until_the_choice_is_embedded(
    api,
    private_dir,
    provider,  # noqa: F811
    action,
):
    client, factory, _ = api
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
        patch("app.knowledge.dispatch_embeddings") as embed_dispatch,
        provider(),
    ):
        result = add_page(client, factory)
        assert client.post(f"{result['status_url']}/embed").status_code == 202
        embed_document(jobs(factory, result["id"], "embedding")[0])
        assert client.get(result["status_url"]).json()["status"] == "Ready"
        old_chunks = chunk_ids(factory, result["id"])

        client.post(f"{result['status_url']}/refresh")
        staging = run_staging(factory, result["id"], NEW_PAGE)
        decide(client, result, action)
        [embed_job] = jobs(factory, str(staging.id), "embedding")
        embed_dispatch.assert_called_with(UUID(embed_job), staging.id)
        # Old version still searchable; the staging copy is never a search result.
        during = client.get(result["status_url"]).json()
        assert during["status"] == "Ready" and during["refresh"]["stage"] == "embedding_pending"
        assert chunk_ids(factory, result["id"]) == old_chunks
        found = client.post("/knowledge/search", json={"query": "garden"}).json()["items"]
        assert {item["document_id"] for item in found} == {result["id"]}
        assert client.post(f"{result['status_url']}/embed").status_code == 409

        embed_document(embed_job)
        after = client.get(result["status_url"]).json()
        assert after["status"] == "Ready"
        assert after["refresh_result"] == ("replaced" if action == "replace" else "appended")
        assert after["embedded_chunk_count"] == after["chunk_count"] > 0
        assert "opens at nine" in after["text"]
        new_chunks = chunk_ids(factory, result["id"])
        if action == "replace":
            assert new_chunks.isdisjoint(old_chunks)
        else:
            assert old_chunks < new_chunks
        assert staging_of(factory, result["id"]) is None
        assert len(stored_files(private_dir)) == 1


def test_searchable_page_needs_embeddings_to_replace_or_append(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    with factory.begin() as session:
        session.get(KnowledgeDocument, UUID(result["id"])).status = "Ready"
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    with patch("app.knowledge.configured", return_value=False):
        response = decide(client, result, "replace")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "embedding_not_configured"
    assert client.get(result["status_url"]).json()["refresh"]["stage"] == "awaiting_decision"
    assert decide(client, result, "keep").json()["refresh_result"] == "kept"


def test_failed_refresh_keeps_the_old_version_and_can_be_tried_again(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    old_chunks = chunk_ids(factory, result["id"])
    client.post(f"{result['status_url']}/refresh")
    staging = staging_of(factory, result["id"])
    with patch("app.worker.fetch_page", side_effect=FetchError("url_timeout")):
        process_text(jobs(factory, str(staging.id))[0])
    failed = client.get(result["status_url"]).json()
    assert failed["refresh"]["status"] == "Failed"
    assert failed["refresh"]["error_code"] == "url_timeout"
    assert failed["stage"] == "text_prepared" and failed["error_code"] is None
    assert chunk_ids(factory, result["id"]) == old_chunks

    assert client.post(f"{result['status_url']}/refresh").status_code == 202
    assert staging_of(factory, result["id"]).id != staging.id
    run_staging(factory, result["id"], NEW_PAGE)
    assert decide(client, result, "replace").json()["refresh_result"] == "replaced"


def test_deleting_during_a_refresh_removes_the_staging_copy_and_its_page(api, private_dir):
    client, factory, _ = api
    result = add_page(client, factory)
    client.post(f"{result['status_url']}/refresh")
    run_staging(factory, result["id"], NEW_PAGE)
    assert len(stored_files(private_dir)) == 2
    assert client.delete(result["status_url"]).status_code == 200
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
    assert decide(client, result, "keep").json()["error"]["message"] == "refresh_not_awaiting"
    assert client.get(f"{result['status_url']}/refresh-changes").status_code == 409


def test_every_new_chunk_carries_the_date_it_was_added(api, private_dir):
    client, factory, _ = api
    pasted = client.post("/knowledge/text", json={"title": "t", "text": "Dated text"}).json()
    process_text(jobs(factory, pasted["id"])[0])
    with factory() as session:
        [chunk] = session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == UUID(pasted["id"]))
        ).all()
    assert len(chunk.source_location["added_on"]) == 10


def test_writer_is_told_newer_sources_win():
    from app.generation import PROMPT_VERSION, SYSTEM

    assert PROMPT_VERSION == "grounded-post-v5"
    assert "source_location.added_on" in " ".join(SYSTEM.split())
    assert "most recently added version" in " ".join(SYSTEM.split())


def test_chunks_from_before_dates_existed_use_their_document_date():
    from datetime import UTC, datetime

    from app.retrieval import rows

    chunk = KnowledgeChunk(document_id=UUID(int=1), content="x", source_location={"char_start": 0})
    chunk.id = UUID(int=2)
    created = datetime(2026, 10, 25, 9, tzinfo=UTC)
    [row] = rows([(chunk, "Title", created, 0.1)])
    assert row["source_location"] == {"added_on": "2026-10-25", "char_start": 0}
    chunk.source_location = {"added_on": "2026-10-30"}
    assert rows([(chunk, "Title", created, 0.1)])[0]["source_location"]["added_on"] == "2026-10-30"
