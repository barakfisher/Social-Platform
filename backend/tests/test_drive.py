"""The Drive client (SP-30) against a mocked Drive: no network, no real key."""

import json
from unittest.mock import patch

import httpx
import pytest

from app import drive
from app.config import get_settings
from app.drive import API, GOOGLE_DOC_TYPE, SCOPES, DriveError, DriveFile

RealClient = httpx.Client
FOLDER = "1FakeFolderIdForTests0000000000000"
SERVICE_EMAIL = "reader@example-project.iam.gserviceaccount.com"


@pytest.fixture
def drive_settings(tmp_path):
    """A fake key file built here; tests never read a real key or .env."""
    settings = get_settings()
    original = settings.model_copy(deep=True)
    key = tmp_path / "service-account.json"
    key.write_text(json.dumps({"type": "service_account", "client_email": SERVICE_EMAIL}))
    settings.google_service_account_file = str(key)
    yield settings
    for field in type(settings).model_fields:
        setattr(settings, field, getattr(original, field))


@pytest.fixture
def mocked(drive_settings):
    """Routes Drive calls to a handler and records the requests."""
    requests: list[httpx.Request] = []

    def install(handler):
        def recorded(request):
            requests.append(request)
            return handler(request)

        return patch(
            "app.drive.http_client",
            side_effect=lambda: RealClient(
                transport=httpx.MockTransport(recorded), follow_redirects=False
            ),
        )

    with patch("app.drive.access_token", return_value="test-token"):
        yield install, requests


def item(file_id, name, mime="text/plain", modified="2026-11-02T10:00:00.000Z"):
    return {"id": file_id, "name": name, "mimeType": mime, "modifiedTime": modified}


@pytest.mark.parametrize(
    "value",
    [
        FOLDER,
        f"https://drive.google.com/drive/folders/{FOLDER}",
        f"https://drive.google.com/drive/folders/{FOLDER}?usp=sharing",
        f"https://drive.google.com/drive/u/1/folders/{FOLDER}",
        f"https://drive.google.com/open?id={FOLDER}",
        f"  {FOLDER}  ",
    ],
)
def test_folder_links_and_ids_give_the_folder_id(value):
    assert drive.folder_id(value) == FOLDER


@pytest.mark.parametrize(
    "value",
    [
        "",
        "short",
        f"{FOLDER}' or name contains '",
        f"https://evil.example/drive/folders/{FOLDER}",
        f"http://drive.google.com/drive/folders/{FOLDER}",
        "../../files",
    ],
)
def test_anything_else_is_refused_before_a_request(value):
    with pytest.raises(DriveError) as raised:
        drive.folder_id(value)
    assert raised.value.code == "drive_folder_invalid"


@pytest.mark.parametrize(
    ("name", "mime", "form"),
    [
        ("Itai's posts", GOOGLE_DOC_TYPE, "doc"),
        ("guide.PDF", "application/pdf", "pdf"),
        ("notes.md", "text/markdown", "text"),
        ("notes.txt", "text/plain", "text"),
        ("budget", "application/vnd.google-apps.spreadsheet", None),
        ("sub", drive.FOLDER_TYPE, None),
        ("photo.jpg", "image/jpeg", None),
        ("report.docx", "application/octet-stream", None),
    ],
)
def test_only_the_upload_formats_and_google_docs_are_imported(name, mime, form):
    assert DriveFile("x" * 12, name, mime, "t").form == form


def test_configuration_comes_from_the_key_file(drive_settings, tmp_path):
    assert drive.configured() and drive.service_account_email() == SERVICE_EMAIL
    drive_settings.google_service_account_file = str(tmp_path / "missing.json")
    assert not drive.configured() and drive.service_account_email() is None
    drive_settings.google_service_account_file = ""
    assert not drive.configured()
    with pytest.raises(DriveError) as raised:
        drive.access_token()
    assert raised.value.code == "drive_not_configured"


def test_the_token_asks_only_for_read_access():
    assert SCOPES == ["https://www.googleapis.com/auth/drive.readonly"]


def test_listing_pages_through_the_folder_on_googles_host_only(mocked):
    install, requests = mocked
    pages = {
        None: {"files": [item("a" * 12, "one.txt")], "nextPageToken": "next-page"},
        "next-page": {"files": [item("b" * 12, "Doc", GOOGLE_DOC_TYPE)]},
    }
    with install(
        lambda request: httpx.Response(200, json=pages[request.url.params.get("pageToken")])
    ):
        files = drive.list_folder(FOLDER)
    assert [f.id for f in files] == ["a" * 12, "b" * 12]
    assert [f.form for f in files] == ["text", "doc"]
    for request in requests:
        assert str(request.url).startswith(f"{API}/files?")
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.url.params["q"] == f"'{FOLDER}' in parents and trashed = false"


def test_a_folder_over_the_limit_fails_whole(mocked, drive_settings):
    install, _ = mocked
    drive_settings.drive_max_files = 1
    listing = {"files": [item("a" * 12, "one.txt"), item("b" * 12, "two.txt")]}
    with (
        install(lambda request: httpx.Response(200, json=listing)),
        pytest.raises(DriveError) as raised,
    ):
        drive.list_folder(FOLDER)
    assert raised.value.code == "drive_folder_too_large"


def test_a_file_id_that_is_not_a_drive_id_never_reaches_a_url(mocked):
    install, _ = mocked
    listing = {"files": [item("../../other", "one.txt")]}
    with (
        install(lambda request: httpx.Response(200, json=listing)),
        pytest.raises(DriveError) as raised,
    ):
        drive.list_folder(FOLDER)
    assert raised.value.code == "drive_request_failed"


def test_folder_name_needs_a_folder(mocked):
    install, _ = mocked
    meta = {"id": FOLDER, "name": "מנטורינג", "mimeType": drive.FOLDER_TYPE}
    with install(lambda request: httpx.Response(200, json=meta)):
        assert drive.folder_name(FOLDER) == "מנטורינג"
    with (
        install(lambda request: httpx.Response(200, json={**meta, "mimeType": GOOGLE_DOC_TYPE})),
        pytest.raises(DriveError) as raised,
    ):
        drive.folder_name(FOLDER)
    assert raised.value.code == "drive_not_a_folder"


def test_google_docs_are_exported_as_text_and_files_downloaded_as_is(mocked):
    install, requests = mocked
    with install(lambda request: httpx.Response(200, content=b"body")):
        drive.download(DriveFile("a" * 12, "Doc", GOOGLE_DOC_TYPE, "t"))
        drive.download(DriveFile("b" * 12, "guide.pdf", "application/pdf", "t"))
    assert requests[0].url.path == f"/drive/v3/files/{'a' * 12}/export"
    assert requests[0].url.params["mimeType"] == "text/plain"
    assert requests[1].url.path == f"/drive/v3/files/{'b' * 12}"
    assert requests[1].url.params["alt"] == "media"


def test_downloads_stop_at_the_upload_limit(mocked, drive_settings):
    install, _ = mocked
    drive_settings.upload_max_bytes = 1024
    oversized = b"x" * (drive_settings.upload_max_bytes + 1)
    with (
        install(lambda request: httpx.Response(200, content=oversized)),
        pytest.raises(DriveError) as raised,
    ):
        drive.download(DriveFile("a" * 12, "big.txt", "text/plain", "t"))
    assert raised.value.code == "file_too_large" and not raised.value.transient


def reason(code):
    return {"error": {"errors": [{"reason": code}]}}


@pytest.mark.parametrize(
    ("response", "code", "transient"),
    [
        (httpx.Response(404), "drive_not_shared", False),
        (
            httpx.Response(403, json=reason("insufficientFilePermissions")),
            "drive_not_shared",
            False,
        ),
        (httpx.Response(403, json=reason("userRateLimitExceeded")), "drive_unavailable", True),
        (httpx.Response(403, json=reason("exportSizeLimitExceeded")), "file_too_large", False),
        (httpx.Response(401), "drive_key_invalid", False),
        (httpx.Response(429), "drive_unavailable", True),
        (httpx.Response(503), "drive_unavailable", True),
        # A redirect is never followed, so it cannot lead the token to another host.
        (
            httpx.Response(302, headers={"Location": "https://evil.example/"}),
            "drive_request_failed",
            False,
        ),
    ],
)
def test_drive_answers_map_to_codes(mocked, response, code, transient):
    install, requests = mocked
    with install(lambda request: response), pytest.raises(DriveError) as raised:
        drive.folder_name(FOLDER)
    assert (raised.value.code, raised.value.transient) == (code, transient)
    assert len(requests) == 1


def test_network_failures_are_transient(mocked):
    install, _ = mocked

    def unreachable(request):
        raise httpx.ConnectError("down", request=request)

    with install(unreachable), pytest.raises(DriveError) as raised:
        drive.list_folder(FOLDER)
    assert (raised.value.code, raised.value.transient) == ("drive_unavailable", True)


@pytest.mark.parametrize(
    "listing",
    [
        {},
        {"files": None},
        {"files": [], "incompleteSearch": True},
        {"files": [{"id": "a" * 12, "name": "x.txt", "mimeType": "text/plain"}]},
    ],
)
def test_a_listing_that_is_not_whole_fails_instead_of_reading_as_empty(mocked, listing):
    install, _ = mocked
    with (
        install(lambda request: httpx.Response(200, json=listing)),
        pytest.raises(DriveError) as raised,
    ):
        drive.list_folder(FOLDER)
    assert raised.value.code == "drive_request_failed"


def test_a_key_naming_another_token_endpoint_is_refused(drive_settings, tmp_path):
    key = tmp_path / "other.json"
    key.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": SERVICE_EMAIL,
                "private_key": "unused",
                "token_uri": "https://evil.example/token",
            }
        )
    )
    drive_settings.google_service_account_file = str(key)
    with (
        patch(
            "app.drive.service_account.Credentials.from_service_account_file",
            side_effect=lambda *a, **k: type(
                "C", (), {"_token_uri": "https://evil.example/token"}
            )(),
        ),
        pytest.raises(DriveError) as raised,
    ):
        drive.access_token()
    assert raised.value.code == "drive_key_invalid"


def test_the_production_client_follows_no_redirects_and_ignores_proxies():
    with drive.http_client() as client:
        assert client.follow_redirects is False
        assert client.trust_env is False
