"""A Knowledge Base document is knowledge or sample posts (SP-29)."""

import pytest
from sqlalchemy import func, select

from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.worker import process_text
from tests.test_knowledge import job_for
from tests.test_refresh import (
    NEW_PAGE,
    add_page,
    decide,
    private_dir,  # noqa: F401  (fixture used by name)
    run_staging,
)
from tests.test_uploads import upload

KINDS = ("knowledge", "sample_posts")


def add_text(client, kind=None, text="The community garden opens at eight every day."):
    body = {"title": "Garden", "text": text}
    if kind is not None:
        body["kind"] = kind
    return client.post("/knowledge/text", json=body)


def counts(factory):
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(IngestionJob)),
            session.scalar(select(func.count()).select_from(KnowledgeChunk)),
        )


def test_a_document_is_knowledge_unless_marked(api):
    client, factory, _ = api
    result = add_text(client).json()
    assert result["kind"] == "knowledge"
    marked = add_text(client, "sample_posts", "Our first post, as published.").json()
    assert marked["kind"] == "sample_posts"
    listed = {item["id"]: item["kind"] for item in client.get("/knowledge").json()["items"]}
    assert listed == {result["id"]: "knowledge", marked["id"]: "sample_posts"}


def test_files_and_web_pages_take_a_kind(api, private_dir):  # noqa: F811
    client, _, _ = api
    file = upload(client, b"Our post.", "posts.txt", kind="sample_posts")
    assert file.status_code == 202 and file.json()["kind"] == "sample_posts"
    plain = upload(client, b"Opening hours.", "hours.txt")
    assert plain.json()["kind"] == "knowledge"
    page = client.post(
        "/knowledge/url", json={"url": "https://garden.example/posts", "kind": "sample_posts"}
    )
    assert page.status_code == 202 and page.json()["kind"] == "sample_posts"


@pytest.mark.parametrize("kind", ["posts", "", None, 1])
def test_an_unknown_kind_is_refused_everywhere(api, private_dir, kind):  # noqa: F811
    client, factory, dispatch = api
    text = client.post("/knowledge/text", json={"title": "Garden", "text": "Open.", "kind": kind})
    assert text.status_code == 422
    page = client.post("/knowledge/url", json={"url": "https://a.example/", "kind": kind})
    assert page.status_code == 422
    if isinstance(kind, str):
        assert upload(client, b"text", "a.txt", kind=kind).status_code == 422
    document = add_text(client).json()
    response = client.patch(document["status_url"], json={"kind": kind})
    assert response.status_code == 422
    assert client.get(document["status_url"]).json()["kind"] == "knowledge"


def test_extra_fields_cannot_ride_along_a_kind_change(api):
    client, _, _ = api
    document = add_text(client).json()
    response = client.patch(
        document["status_url"], json={"kind": "sample_posts", "title": "Renamed"}
    )
    assert response.status_code == 422
    assert client.get(document["status_url"]).json()["title"] == "Garden"


@pytest.mark.parametrize("prepared", [False, True])
def test_changing_the_kind_is_free_at_any_stage(api, prepared):
    client, factory, dispatch = api
    document = add_text(client).json()
    if prepared:
        process_text(job_for(factory, document["id"]))
    before = counts(factory)
    state = client.get(document["status_url"]).json()
    for kind in ("sample_posts", "knowledge", "sample_posts"):
        response = client.patch(document["status_url"], json={"kind": kind})
        assert response.status_code == 200 and response.json()["kind"] == kind
    # Nothing is prepared, embedded or queued again.
    assert counts(factory) == before
    assert dispatch.call_count == 1
    after = client.get(document["status_url"]).json()
    assert {k: v for k, v in after.items() if k != "kind"} == {
        k: v for k, v in state.items() if k != "kind"
    }


@pytest.mark.parametrize("choice", ["replace", "append"])
def test_a_reloaded_web_page_keeps_its_kind(api, private_dir, choice):  # noqa: F811
    client, factory, _ = api
    result = add_page(client, factory)
    client.patch(result["status_url"], json={"kind": "sample_posts"})
    client.post(f"{result['status_url']}/refresh")
    staging = run_staging(factory, result["id"], NEW_PAGE)
    assert decide(client, result, choice).json()["kind"] == "sample_posts"
    # The hidden staging copy cannot be marked through the API.
    assert client.patch(f"/knowledge/{staging.id}", json={"kind": "knowledge"}).status_code == 404


def test_a_missing_document_is_not_found(api):
    client, _, _ = api
    response = client.patch(
        "/knowledge/00000000-0000-0000-0000-000000000000", json={"kind": "sample_posts"}
    )
    assert response.status_code == 404


def test_the_database_refuses_an_unknown_kind(api):
    _, factory, _ = api
    from sqlalchemy.exc import IntegrityError

    from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope

    with pytest.raises(IntegrityError), factory.begin() as session:
        seed_local_scope(session)
        session.add(
            KnowledgeDocument(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                title="Bad",
                source_type="text",
                source_text="x",
                kind="posts",
            )
        )
        session.flush()


def test_the_kinds_the_api_offers_are_the_kinds_the_database_accepts():
    from typing import get_args

    from app.knowledge import DocumentKind

    assert get_args(DocumentKind) == KINDS
    constraint = next(
        c for c in KnowledgeDocument.__table__.constraints if c.name == "knowledge_documents_kind"
    )
    assert all(f"'{kind}'" in str(constraint.sqltext) for kind in KINDS)


def test_rows_written_without_a_kind_are_knowledge(api):
    # The migration's server default: rows from before it, and any insert that omits the
    # column, read back as knowledge.
    _, factory, _ = api
    from sqlalchemy import text

    from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope

    with factory.begin() as session:
        seed_local_scope(session)
        kind = session.execute(
            text(
                "INSERT INTO knowledge_documents (id, user_id, workspace_id, title, source_type,"
                " status, processing_stage, created_at, updated_at)"
                " VALUES (gen_random_uuid(), :user, :workspace, 'Old', 'text', 'Ready', 'ready',"
                " now(), now()) RETURNING kind"
            ),
            {"user": LOCAL_USER_ID, "workspace": LOCAL_WORKSPACE_ID},
        ).scalar_one()
    assert kind == "knowledge"


def test_a_kind_change_does_not_count_as_an_update(api):
    # Topic ideas sample the most recently updated documents; a kind is not new content.
    client, factory, _ = api
    document = add_text(client).json()
    with factory() as session:
        before = session.get(KnowledgeDocument, document["id"]).updated_at
    client.patch(document["status_url"], json={"kind": "sample_posts"})
    with factory() as session:
        after = session.get(KnowledgeDocument, document["id"])
        assert after.kind == "sample_posts" and after.updated_at == before
