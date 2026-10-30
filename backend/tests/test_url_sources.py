from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.extraction import ExtractionError, extract_html
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument, User, Workspace
from app.web_fetch import FetchError
from app.worker import process_text

PAGE = """<!doctype html><html lang="he"><head><title>שעות פתיחה | גינה</title></head>
<body><nav>תפריט ראשי · צור קשר · התחברות</nav><main><article>
<h1>שעות הפתיחה של הגינה הקהילתית</h1>
<p>הגינה הקהילתית פתוחה בכל יום משמונה בבוקר ועד שבע בערב, לתושבים ולמבקרים.</p>
<h2>ערבי מתנדבים</h2>
<p>בכל יום שלישי מתקיים ערב מתנדבים בין שש לשמונה, עם כלים ושתילים לכל המשתתפים.</p>
</article></main><footer>כל הזכויות שמורות</footer></body></html>""".encode()


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "source_storage_dir", str(tmp_path / "sources"))
    return tmp_path / "sources"


def stored_files(directory):
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def job_for(factory, document_id):
    with factory() as session:
        return str(
            session.scalar(
                select(IngestionJob.id).where(IngestionJob.document_id == UUID(document_id))
            )
        )


def test_html_extraction_keeps_headings_and_drops_navigation():
    text, title = extract_html(PAGE)
    assert text.startswith("# שעות הפתיחה של הגינה הקהילתית")
    assert "## ערבי מתנדבים" in text
    assert "תפריט ראשי" not in text and "כל הזכויות שמורות" not in text
    assert title


@pytest.mark.parametrize(
    "page", [b"", b"<html><body><script>render()</script></body></html>", b"\x00\x01\x02"]
)
def test_pages_without_main_text_fail_as_no_content(page):
    with pytest.raises(ExtractionError) as raised:
        extract_html(page)
    assert raised.value.code in ("url_no_content", "url_parse_failed")


def test_url_is_fetched_by_the_worker_stored_privately_and_titled(api, private_dir):
    client, factory, dispatch = api
    response = client.post("/knowledge/url", json={"url": "https://Garden.example/hours#top"})
    assert response.status_code == 202
    result = response.json()
    assert result["source_type"] == "url"
    assert result["url"] == "https://garden.example/hours"
    assert result["filename"] is None
    assert result["title"] == "garden.example/hours"
    job_id = job_for(factory, result["id"])
    dispatch.assert_called_once_with(args=[job_id], task_id=job_id)
    assert stored_files(private_dir) == []  # Nothing is fetched in the request.

    with patch("app.worker.fetch_page", return_value=PAGE) as fetch:
        process_text(job_id)
    fetch.assert_called_once_with("https://garden.example/hours")
    prepared = client.get(result["status_url"]).json()
    assert prepared["stage"] == "text_prepared"
    assert prepared["title"] != "garden.example/hours"  # The page's own title.
    assert "## ערבי מתנדבים" in prepared["text"]
    [key] = stored_files(private_dir)
    assert (private_dir / key).read_bytes() == PAGE
    with factory() as session:
        chunks = session.scalars(select(KnowledgeChunk)).all()
        assert chunks and "page_start" not in chunks[0].source_location

    duplicate = client.post("/knowledge/url", json={"url": "https://garden.example/hours"})
    assert duplicate.json()["id"] == result["id"] and duplicate.json()["duplicate"] is True

    assert client.delete(result["status_url"]).status_code == 200
    assert stored_files(private_dir) == []


def test_owner_title_is_kept(api, private_dir):
    client, factory, _ = api
    result = client.post(
        "/knowledge/url", json={"url": "https://garden.example/", "title": "  Our hours "}
    ).json()
    assert result["title"] == "Our hours"
    with patch("app.worker.fetch_page", return_value=PAGE):
        process_text(job_for(factory, result["id"]))
    assert client.get(result["status_url"]).json()["title"] == "Our hours"


def test_fetch_failures_are_stored_and_retry_fetches_again(api, private_dir):
    client, factory, dispatch = api
    result = client.post("/knowledge/url", json={"url": "https://garden.example/"}).json()
    job_id = job_for(factory, result["id"])
    with patch("app.worker.fetch_page", side_effect=FetchError("url_blocked_address")):
        process_text(job_id)
    failed = client.get(result["status_url"]).json()
    assert failed["status"] == "Failed" and failed["error_code"] == "url_blocked_address"
    assert stored_files(private_dir) == []

    # A fetched page with no text (a script-only app) is kept; "Process again" fetches a fresh copy.
    with patch(
        "app.worker.fetch_page", return_value=b"<html><body><script>render()</script></body></html>"
    ):
        assert client.post(f"{result['status_url']}/retry").status_code == 202
        process_text(job_id)
    assert client.get(result["status_url"]).json()["error_code"] == "url_no_content"
    [old_copy] = stored_files(private_dir)
    with patch("app.worker.fetch_page", return_value=PAGE) as fetch:
        assert client.post(f"{result['status_url']}/retry").status_code == 202
        process_text(job_id)
    fetch.assert_called_once()
    assert client.get(result["status_url"]).json()["stage"] == "text_prepared"
    [new_copy] = stored_files(private_dir)
    assert new_copy != old_copy
    assert dispatch.call_count == 3


def test_page_fetched_for_a_deleted_source_is_not_kept(api, private_dir):
    client, factory, _ = api
    result = client.post("/knowledge/url", json={"url": "https://garden.example/"}).json()
    job_id = job_for(factory, result["id"])

    def fetch_then_delete(url):
        assert client.delete(result["status_url"]).status_code == 200
        return PAGE

    with patch("app.worker.fetch_page", side_effect=fetch_then_delete):
        process_text(job_id)
    assert stored_files(private_dir) == []
    assert client.get(result["status_url"]).status_code == 404


def test_page_is_removed_when_the_write_fails(api, private_dir):
    client, factory, _ = api
    result = client.post("/knowledge/url", json={"url": "https://garden.example/"}).json()
    with (
        patch("app.worker.fetch_page", return_value=PAGE),
        patch("app.worker.chunk_text", side_effect=RuntimeError("database down")),
        pytest.raises(RuntimeError),
    ):
        process_text(job_for(factory, result["id"]))
    assert stored_files(private_dir) == []


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"url": "ftp://garden.example/"}, "url_scheme_unsupported"),
        ({"url": "http://169.254.169.254/latest/meta-data/"}, "url_blocked_address"),
        ({"url": "http://localhost:58073/knowledge"}, "url_port_unsupported"),
        ({"url": "http://localhost/"}, "url_blocked_address"),
        ({"url": "https://user:pw@garden.example/"}, "url_credentials"),
        ({"url": "not a url"}, "url_invalid"),
    ],
)
def test_invalid_urls_create_nothing(api, payload, code):
    client, factory, dispatch = api
    response = client.post("/knowledge/url", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == code
    dispatch.assert_not_called()
    with factory() as session:
        assert session.scalar(select(KnowledgeDocument.id)) is None


@pytest.mark.parametrize(
    "payload",
    [{"url": ""}, {"url": "https://garden.example/", "extra": 1}, {"title": "x"}],
)
def test_malformed_url_requests_are_rejected(api, payload):
    client, _, dispatch = api
    assert client.post("/knowledge/url", json=payload).status_code == 422
    dispatch.assert_not_called()


def test_other_workspace_url_source_cannot_be_read_retried_or_deleted(api):
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
            title="Private page",
            source_type="url",
            source_reference="https://garden.example/private",
        )
        session.add(document)
        session.flush()
        path = f"/knowledge/{document.id}"
    assert client.get(path).status_code == 404
    assert client.post(path + "/retry").status_code == 404
    assert client.delete(path).status_code == 404
    dispatch.assert_not_called()
