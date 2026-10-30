import json
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.write_guard import is_json_content_type

# A host the API trusts; TestClient's default "testserver" is not one.
client = TestClient(app, base_url="http://127.0.0.1")
ALLOWED_ORIGIN = get_settings().cors_origins[0]
DOCUMENT = uuid4()
EMBED = f"/knowledge/{DOCUMENT}/embed"
GENERATION = json.dumps({"request_key": str(uuid4()), "topic": "Volunteer evenings"}).encode()
# Every write route a page could target, with the body each one takes (None: no body).
WRITES = [
    ("POST", "/generation", GENERATION),
    ("POST", f"/generation/{uuid4()}/review", b"{}"),
    ("POST", "/generation/topic-suggestions", b"{}"),
    ("POST", f"/posts/{uuid4()}/review", b"{}"),
    ("POST", EMBED, None),
    ("POST", f"/knowledge/{DOCUMENT}/retry", None),
    ("POST", f"/knowledge/{DOCUMENT}/refresh", None),
    ("POST", "/knowledge/text", b"{}"),
    ("POST", "/knowledge/files?filename=notes.pdf", b"%PDF-1.4"),
    ("POST", "/knowledge/url", b'{"url": "https://garden.example/"}'),
    ("POST", "/dev/jobs/probe", None),
    ("PUT", "/brand", b"{}"),
    ("DELETE", f"/knowledge/{DOCUMENT}", None),
    ("DELETE", f"/posts/{uuid4()}", None),
]


@pytest.fixture
def embed_handler():
    """Starting embeddings is a paid write with no body, so a cross-site no-cors POST needs
    no Content-Type at all. The stand-in shows whether a request reached the handler; it
    stops there, so nothing touches a database or a provider."""
    with patch("app.knowledge.configured", return_value=False) as reached:
        yield reached


@pytest.fixture
def generation_handler():
    with (
        patch("app.generation.generate_locked", return_value={"id": "reached"}) as reached,
        patch("app.generation.generation_lock") as lock,
    ):
        lock.return_value.__enter__.return_value = True
        yield reached


@pytest.fixture
def no_handlers():
    """Fails the test if a rejected write reaches the database or a provider."""
    with (
        patch("app.db.engine.connect", side_effect=AssertionError("database reached")),
        # The real network transport; TestClient uses its own in-process one.
        patch.object(
            httpx.HTTPTransport, "handle_request", side_effect=AssertionError("network reached")
        ),
    ):
        yield


def test_cross_site_bodyless_post_does_not_reach_a_paid_handler(embed_handler):
    response = client.post(
        EMBED, headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "cross_site_request"
    embed_handler.assert_not_called()


@pytest.mark.parametrize("method,path,body", WRITES)
@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
        # Another local project: same-site with the API, but not an allowed origin.
        {"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-site"},
        {"Origin": "null"},
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_write_from_a_disallowed_page_is_rejected(no_handlers, method, path, body, headers):
    content_type = {"Content-Type": "application/json"} if body else {}
    response = client.request(method, path, content=body, headers={**headers, **content_type})
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "cross_site_request"
    assert error["request_id"] == response.headers["x-request-id"]


def test_port_3000_is_not_an_allowed_origin():
    # Port 3000 belongs to other local projects (owner decision, SP-23).
    assert not any(origin.endswith(":3000") for origin in Settings(_env_file=None).cors_origins)


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain;application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/jsonx",
        None,
    ],
)
def test_write_body_must_be_json(no_handlers, content_type):
    headers = {"Content-Type": content_type} if content_type else {}
    response = client.post("/generation", content=GENERATION, headers=headers)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "invalid_content_type"


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=x",
        "application/json",
        "application/pdf",
        None,
    ],
)
def test_uploads_must_be_raw_octet_stream(no_handlers, content_type):
    # Every type a page can send without a preflight is refused; so is JSON on this route.
    headers = {"Content-Type": content_type} if content_type else {}
    response = client.post(
        "/knowledge/files?filename=notes.pdf", content=b"%PDF-1.4", headers=headers
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "invalid_content_type"


def test_octet_stream_is_accepted_only_on_the_upload_route(no_handlers):
    response = client.post(
        "/generation", content=GENERATION, headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 415


def test_allowed_page_json_write_reaches_the_handler(generation_handler):
    response = client.post(
        "/generation",
        content=GENERATION,
        headers={
            "Origin": ALLOWED_ORIGIN,
            # A page on 53073 calling the API on 58073 is same-site, not same-origin.
            "Sec-Fetch-Site": "same-site",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    assert response.status_code == 200
    generation_handler.assert_called_once()


@pytest.mark.parametrize("fetch_site", ["same-origin", "none"])
def test_trusted_fetch_site_without_origin_reaches_the_handler(embed_handler, fetch_site):
    assert client.post(EMBED, headers={"Sec-Fetch-Site": fetch_site}).status_code == 503
    embed_handler.assert_called_once()


def test_non_browser_clients_are_allowed(embed_handler, generation_handler):
    # The Next.js proxy, curl and scripts send neither Origin nor Sec-Fetch-Site.
    assert client.post(EMBED).status_code == 503
    assert client.post("/generation", json=json.loads(GENERATION)).status_code == 200
    embed_handler.assert_called_once()
    generation_handler.assert_called_once()


def test_reads_and_preflight_are_never_blocked():
    evil = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    assert client.get("/health/live", headers=evil).status_code == 200
    preflight = client.options(
        "/generation",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_untrusted_host_is_rejected(no_handlers, method):
    # DNS rebinding: an attacker's name resolving to 127.0.0.1 still sends its own Host.
    rebound = TestClient(app, base_url="http://rebind.evil.example:58073")
    assert rebound.request(method, "/health/live").status_code == 400


def test_untrusted_host_stops_writes_the_origin_rule_allows(embed_handler):
    # A rebinding page's write looks same-origin; only the Host check stops it.
    rebound = TestClient(app, base_url="http://rebind.evil.example:58073")
    assert rebound.post(EMBED, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 400
    embed_handler.assert_not_called()


@pytest.mark.parametrize(
    "origin",
    [f"{ALLOWED_ORIGIN}/", ALLOWED_ORIGIN.upper(), ALLOWED_ORIGIN.replace("http", "https")],
)
def test_origin_must_match_exactly(embed_handler, origin):
    assert client.post(EMBED, headers={"Origin": origin}).status_code == 403
    embed_handler.assert_not_called()


def test_body_detection_fails_closed(no_handlers, embed_handler):
    # Chunked bodies, odd Content-Length spellings and bodies on bodiless routes are checked.
    chunked = client.post("/generation", content=iter([GENERATION]))
    assert chunked.status_code == 415
    padded = client.post(EMBED, headers={"Content-Length": "00"})
    assert padded.status_code == 415
    allowed_page = client.post(
        EMBED, content=b"{}", headers={"Origin": ALLOWED_ORIGIN, "Content-Type": "text/plain"}
    )
    assert allowed_page.status_code == 415
    embed_handler.assert_not_called()


@pytest.mark.parametrize("setting", ["ALLOWED_HOSTS", "CORS_ORIGINS"])
def test_wildcards_are_refused(monkeypatch, setting):
    monkeypatch.setenv(setting, '["*"]')
    with pytest.raises(ValueError, match="exact values"):
        Settings(_env_file=None)


def test_json_content_type_rule():
    assert is_json_content_type("application/json")
    assert is_json_content_type("Application/JSON; charset=utf-8")
    for value in (None, "", "text/plain;application/json", "application/jsonx"):
        assert not is_json_content_type(value)
