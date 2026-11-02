"""Drive folder sync (SP-30) against a fake Drive: no network, no real key."""

from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.drive import GOOGLE_DOC_TYPE, DriveError, DriveFile
from app.drive_sync import SYNC_INTERVAL, SYNC_STALE, due_folders, sync_folder
from app.models import DriveFolder, IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.worker import embed_document, process_text
from tests.test_embeddings import embedding_key, provider  # noqa: F401
from tests.test_uploads import pdf

FOLDER = "1FakeFolderIdForTests0000000000000"
LINK = f"https://drive.google.com/drive/folders/{FOLDER}?usp=sharing"
DOC_ID = "doc1234567890"
POSTS = "פוסט ראשון על מנטורינג.\n\nפוסט שני על צמיחה מקצועית."
NEW_POSTS = "פוסט שלישי על הקשבה בפגישות מנטורינג."


class FakeDrive:
    """The folder as Drive would list it, with each file's content."""

    def __init__(self):
        self.files: dict[str, tuple[DriveFile, bytes]] = {}
        self.downloads: list[str] = []
        self.listing_error: DriveError | None = None
        self.download_error: DriveError | None = None

    def put(
        self, file_id, name, content: bytes, mime="text/plain", modified="2026-11-01T10:00:00Z"
    ):
        self.files[file_id] = (DriveFile(file_id, name, mime, modified), content)

    def folder_name(self, folder_id):
        if self.listing_error:
            raise self.listing_error
        assert folder_id == FOLDER
        return "מנטורינג"

    def list_folder(self, folder_id):
        if self.listing_error:
            raise self.listing_error
        return [file for file, _ in self.files.values()]

    def download(self, file):
        if self.download_error:
            raise self.download_error
        self.downloads.append(file.id)
        return self.files[file.id][1]


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "source_storage_dir", str(tmp_path / "sources"))
    return tmp_path / "sources"


@pytest.fixture
def fake(api, private_dir):
    folder = FakeDrive()
    folder.put(DOC_ID, "פוסטים של איתי מהפייסבוק", POSTS.encode(), GOOGLE_DOC_TYPE)
    with (
        patch("app.drive.configured", return_value=True),
        patch(
            "app.drive.service_account_email", return_value="reader@example.iam.gserviceaccount.com"
        ),
        patch("app.drive.folder_name", side_effect=folder.folder_name),
        patch("app.drive.list_folder", side_effect=folder.list_folder),
        patch("app.drive.download", side_effect=folder.download),
        patch("app.drive_sync.embedding_lock", return_value=nullcontext(True)),
        patch("app.worker.sync_drive_folder.apply_async") as sync_dispatch,
    ):
        yield folder, sync_dispatch


def connect(client, kind="sample_posts"):
    response = client.post("/knowledge/drive-folders", json={"folder": LINK, "kind": kind})
    assert response.status_code == 202, response.text
    return response.json()


def documents(factory, folder_row_id):
    with factory() as session:
        return list(
            session.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.drive_folder_id == UUID(folder_row_id))
                .order_by(KnowledgeDocument.created_at)
            )
        )


def originals(factory, folder_row_id):
    return [d for d in documents(factory, folder_row_id) if d.replaces_id is None]


def run_text_jobs(factory, dispatch):
    """Runs every ingestion job the sync queued, as the worker would."""
    for call in dispatch.call_args_list:
        process_text(call.kwargs["args"][0])
    dispatch.reset_mock()


def folder_of(client, folder_row_id):
    items = client.get("/knowledge/drive-folders").json()["items"]
    return next(item for item in items if item["id"] == folder_row_id)


@contextmanager
def searchable(provider):  # noqa: F811
    with (
        patch("app.worker.embed_document.apply_async"),
        patch("app.worker.embedding_lock", return_value=nullcontext(True)),
        patch("app.knowledge.dispatch_embeddings"),
        provider(),
    ):
        yield


def embed_all(factory, client, document_id):
    assert client.post(f"/knowledge/{document_id}/embed").status_code == 202
    with factory() as session:
        job = session.scalar(
            select(IngestionJob.id).where(
                IngestionJob.document_id == document_id, IngestionJob.kind == "embedding"
            )
        )
    embed_document(str(job))


def test_listing_explains_whom_to_share_with(api, fake):
    client, _, _ = api
    listing = client.get("/knowledge/drive-folders").json()
    assert listing["configured"] is True
    assert listing["service_account_email"] == "reader@example.iam.gserviceaccount.com"


def test_connecting_imports_a_google_doc_with_the_folders_kind_and_it_becomes_ready(
    api,
    fake,
    provider,  # noqa: F811
):
    client, factory, dispatch = api
    _, sync_dispatch = fake
    folder = connect(client)
    assert folder["name"] == "מנטורינג" and folder["status"] == "Pending"
    sync_dispatch.assert_called_once_with(args=[folder["id"]])

    sync_folder(UUID(folder["id"]))
    [document] = originals(factory, folder["id"])
    assert document.source_type == "drive" and document.kind == "sample_posts"
    assert document.title == "פוסטים של איתי מהפייסבוק"
    run_text_jobs(factory, dispatch)
    with searchable(provider):
        embed_all(factory, client, document.id)
    ready = client.get(f"/knowledge/{document.id}").json()
    assert ready["status"] == "Ready" and ready["text"] == POSTS
    assert ready["filename"] == "פוסטים של איתי מהפייסבוק"
    assert ready["drive_folder_id"] == folder["id"]
    after = folder_of(client, folder["id"])
    assert after["status"] == "Ready" and after["document_count"] == 1 and after["synced_at"]


def test_an_unchanged_folder_downloads_nothing(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    downloads = list(drive_folder.downloads)

    sync_folder(UUID(folder["id"]))
    assert drive_folder.downloads == downloads
    dispatch.assert_not_called()
    assert len(documents(factory, folder["id"])) == 1


def test_a_changed_file_replaces_its_text_and_keeps_the_owners_kind(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    [document] = originals(factory, folder["id"])
    client.patch(f"/knowledge/{document.id}", json={"kind": "knowledge"})

    drive_folder.put(
        DOC_ID, "פוסטים של איתי", NEW_POSTS.encode(), GOOGLE_DOC_TYPE, "2026-11-02T09:00:00Z"
    )
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    [after] = documents(factory, folder["id"])
    assert after.id == document.id and after.source_text == NEW_POSTS
    assert after.kind == "knowledge" and after.title == "פוסטים של איתי"
    assert after.drive_modified_at == "2026-11-02T09:00:00Z"
    assert after.refresh_result == "replaced"


def test_a_searchable_file_stays_in_use_until_its_new_version_is_embedded(
    api,
    fake,
    provider,  # noqa: F811
):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    [document] = originals(factory, folder["id"])
    with searchable(provider):
        embed_all(factory, client, document.id)
        with factory() as session:
            old_chunks = set(
                session.scalars(
                    select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == document.id)
                )
            )

        client.patch(f"/knowledge/{document.id}", json={"kind": "knowledge"})
        drive_folder.put(
            DOC_ID, "פוסטים", NEW_POSTS.encode(), GOOGLE_DOC_TYPE, "2026-11-02T09:00:00Z"
        )
        with patch("app.worker.embed_document.apply_async") as embed_dispatch:
            sync_folder(UUID(folder["id"]))
            run_text_jobs(factory, dispatch)
        [embed_call] = embed_dispatch.call_args_list
        during = client.get(f"/knowledge/{document.id}").json()
        assert during["status"] == "Ready" and during["text"] == POSTS
        assert during["refresh"]["stage"] == "embedding_pending"

        embed_document(embed_call.kwargs["args"][0])
    after = client.get(f"/knowledge/{document.id}").json()
    assert after["status"] == "Ready" and after["text"] == NEW_POSTS
    assert after["refresh"] is None and after["kind"] == "knowledge"
    with factory() as session:
        new_chunks = set(
            session.scalars(
                select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == document.id)
            )
        )
    assert new_chunks and new_chunks.isdisjoint(old_chunks)


def test_a_searchable_file_is_not_replaced_while_embeddings_are_off(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    [document] = originals(factory, folder["id"])
    with factory.begin() as session:
        session.get(KnowledgeDocument, document.id).status = "Ready"
    drive_folder.put(DOC_ID, "פוסטים", NEW_POSTS.encode(), GOOGLE_DOC_TYPE, "2026-11-02T09:00:00Z")
    downloads = list(drive_folder.downloads)
    with patch("app.drive_sync.embeddings_configured", return_value=False):
        sync_folder(UUID(folder["id"]))
    assert drive_folder.downloads == downloads
    [after] = documents(factory, folder["id"])
    assert after.source_text == POSTS


def test_a_file_removed_from_the_folder_is_deleted_with_its_stored_copy(api, fake, private_dir):
    client, factory, dispatch = api
    drive_folder, _ = fake
    drive_folder.put("pdf1234567890", "guide.pdf", pdf("Mentoring guide"), "application/pdf")
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    assert len(list(private_dir.iterdir())) == 1
    guide = next(d for d in documents(factory, folder["id"]) if d.drive_file_id == "pdf1234567890")
    assert guide.title == "guide" and "Mentoring guide" in guide.source_text

    del drive_folder.files["pdf1234567890"]
    sync_folder(UUID(folder["id"]))
    assert [d.drive_file_id for d in documents(factory, folder["id"])] == [DOC_ID]
    assert list(private_dir.iterdir()) == []


@pytest.mark.parametrize("code", ["drive_not_shared", "drive_unavailable"])
def test_a_folder_out_of_reach_deletes_nothing(api, fake, code):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)

    drive_folder.listing_error = DriveError(code, transient=code == "drive_unavailable")
    sync_folder(UUID(folder["id"]))
    assert len(documents(factory, folder["id"])) == 1
    after = folder_of(client, folder["id"])
    assert after["status"] == "Failed" and after["error_code"] == code


def test_a_download_outage_stops_the_sync_and_the_next_one_tries_again(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    folder = connect(client)
    drive_folder.download_error = DriveError("drive_unavailable", transient=True)
    sync_folder(UUID(folder["id"]))
    assert documents(factory, folder["id"]) == []
    assert folder_of(client, folder["id"])["error_code"] == "drive_unavailable"

    drive_folder.download_error = None
    sync_folder(UUID(folder["id"]))
    assert len(documents(factory, folder["id"])) == 1
    assert folder_of(client, folder["id"])["status"] == "Ready"


def test_other_files_are_skipped_and_counted(api, fake):
    client, factory, _ = api
    drive_folder, _ = fake
    drive_folder.put("sheet123456789", "budget", b"", "application/vnd.google-apps.spreadsheet")
    drive_folder.put("subfolder12345", "old", b"", "application/vnd.google-apps.folder")
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    after = folder_of(client, folder["id"])
    assert (after["file_count"], after["skipped_count"]) == (1, 2)
    assert drive_folder.downloads == [DOC_ID]


def test_an_unreadable_file_fails_on_its_own_and_is_read_again_once_changed(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    drive_folder.put("text1234567890", "notes.txt", b"\xff\xfe broken")
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    notes = next(d for d in documents(factory, folder["id"]) if d.drive_file_id == "text1234567890")
    assert notes.status == "Failed" and notes.error_code == "file_not_utf8"
    assert folder_of(client, folder["id"])["status"] == "Ready"

    drive_folder.put(
        "text1234567890", "notes.txt", "הערות".encode(), modified="2026-11-02T09:00:00Z"
    )
    dispatch.reset_mock()
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    notes = next(d for d in documents(factory, folder["id"]) if d.drive_file_id == "text1234567890")
    assert notes.processing_stage == "text_prepared" and notes.source_text == "הערות"


@pytest.mark.parametrize(
    ("value", "status", "code"),
    [
        ("not a folder link", 422, "drive_folder_invalid"),
        (LINK, 404, "drive_not_shared"),
    ],
)
def test_connecting_reports_why_a_folder_cannot_be_read(api, fake, value, status, code):
    client, _, _ = api
    drive_folder, sync_dispatch = fake
    drive_folder.listing_error = DriveError("drive_not_shared")
    response = client.post("/knowledge/drive-folders", json={"folder": value})
    assert response.status_code == status
    assert response.json()["error"]["message"] == code
    sync_dispatch.assert_not_called()


def test_connecting_needs_the_key(api, fake):
    client, _, _ = api
    with patch("app.drive.configured", return_value=False):
        response = client.post("/knowledge/drive-folders", json={"folder": LINK})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "drive_not_configured"


def test_the_same_folder_is_connected_once(api, fake):
    client, _, _ = api
    first = connect(client)
    again = client.post("/knowledge/drive-folders", json={"folder": FOLDER}).json()
    assert again["id"] == first["id"] and again["duplicate"] is True


def test_refresh_queues_one_sync_at_a_time(api, fake):
    client, _, _ = api
    _, sync_dispatch = fake
    folder = connect(client)
    client.post(f"/knowledge/drive-folders/{folder['id']}/sync")
    assert sync_dispatch.call_count == 1  # Still queued from connecting.
    sync_folder(UUID(folder["id"]))
    response = client.post(f"/knowledge/drive-folders/{folder['id']}/sync")
    assert response.status_code == 202 and response.json()["status"] == "Pending"
    assert sync_dispatch.call_count == 2


def test_a_lost_sync_shows_as_interrupted_and_can_be_refreshed(api, fake):
    client, factory, _ = api
    _, sync_dispatch = fake
    folder = connect(client)
    with factory.begin() as session:
        row = session.get(DriveFolder, UUID(folder["id"]))
        row.sync_status = "Syncing"
        row.attempted_at = datetime.now(UTC) - SYNC_STALE
    lost = folder_of(client, folder["id"])
    assert (lost["status"], lost["error_code"]) == ("Failed", "drive_sync_interrupted")
    client.post(f"/knowledge/drive-folders/{folder['id']}/sync")
    assert sync_dispatch.call_count == 2


def test_disconnecting_deletes_the_folders_sources_and_files(api, fake, private_dir):
    client, factory, dispatch = api
    drive_folder, _ = fake
    drive_folder.put("pdf1234567890", "guide.pdf", pdf("Mentoring guide"), "application/pdf")
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    assert client.delete(f"/knowledge/drive-folders/{folder['id']}").json() == {"deleted": True}
    assert documents(factory, folder["id"]) == []
    assert list(private_dir.iterdir()) == []
    listed = client.get("/knowledge/drive-folders").json()["items"]
    assert folder["id"] not in {item["id"] for item in listed}
    assert client.post(f"/knowledge/drive-folders/{folder['id']}/sync").status_code == 404


def test_folders_are_due_once_a_day(api, fake):
    client, factory, _ = api
    folder = connect(client)
    row_id = UUID(folder["id"])
    with patch("app.drive_sync.SessionLocal", factory):
        assert row_id in due_folders()  # Never synced.
        sync_folder(row_id)
        assert row_id not in due_folders()
        with factory.begin() as session:
            session.get(DriveFolder, row_id).attempted_at = datetime.now(UTC) - SYNC_INTERVAL
        assert row_id in due_folders()


def test_a_file_that_was_never_read_cannot_be_processed_again(api, fake):
    client, factory, _ = api
    drive_folder, _ = fake
    drive_folder.put("big1234567890", "big.txt", b"")
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    big = next(d for d in documents(factory, folder["id"]) if d.drive_file_id == "big1234567890")
    assert big.error_code == "source_empty"
    response = client.post(f"/knowledge/{big.id}/retry")
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "drive_file_unread"


def test_a_failed_sync_deletes_nothing_even_after_a_file_left(api, fake):
    client, factory, dispatch = api
    drive_folder, _ = fake
    drive_folder.put("text1234567890", "notes.txt", "הערות".encode())
    folder = connect(client)
    sync_folder(UUID(folder["id"]))
    run_text_jobs(factory, dispatch)
    del drive_folder.files["text1234567890"]
    drive_folder.put(DOC_ID, "פוסטים", NEW_POSTS.encode(), GOOGLE_DOC_TYPE, "2026-11-02T09:00:00Z")
    drive_folder.download_error = DriveError("drive_unavailable", transient=True)
    sync_folder(UUID(folder["id"]))
    assert {d.drive_file_id for d in originals(factory, folder["id"])} == {DOC_ID, "text1234567890"}
    assert folder_of(client, folder["id"])["error_code"] == "drive_unavailable"


def test_the_beat_runs_due_folders_every_hour(api, fake):
    from app.worker import celery_app, sync_due_drive_folders

    client, factory, _ = api
    _, sync_dispatch = fake
    entry = celery_app.conf.beat_schedule["sync-drive-folders"]
    assert entry["task"] == sync_due_drive_folders.name
    folder = connect(client)
    sync_dispatch.reset_mock()
    sync_due_drive_folders()
    assert [c.kwargs["args"] for c in sync_dispatch.call_args_list].count([folder["id"]]) == 1
