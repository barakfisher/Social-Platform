import gzip
import socket
from unittest.mock import patch

import httpx
import pytest

from app import web_fetch
from app.config import get_settings
from app.web_fetch import FetchError, fallback_title, fetch_page, is_public, normalize_url

PAGE = b"<html><body><article><h1>Garden</h1><p>Open daily.</p></article></body></html>"
HTML = {"content-type": "text/html; charset=utf-8"}
DNS = {"garden.example": ["93.184.215.14"], "cdn.example": ["2606:4700::1111"]}


def response(status=200, headers=None, content=b""):
    # A streamed body, as from the network; Response(content=...) would be read eagerly.
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(content))


@pytest.fixture
def web(monkeypatch):
    """Requests go to `handler`; names resolve through DNS. Records every request sent."""
    sent: list[httpx.Request] = []
    state = {"handler": lambda request: response(200, headers=HTML, content=PAGE)}

    def transport(request):
        sent.append(request)
        return state["handler"](request)

    monkeypatch.setattr(
        web_fetch,
        "open_client",
        lambda: httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=False),
    )

    def resolve(host):
        if host not in DNS:
            raise FetchError("url_dns_failed")
        return DNS[host]

    monkeypatch.setattr(web_fetch, "resolve", resolve)
    return state, sent


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.5.4",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "2002:a9fe:a9fe::",
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    ],
)
def test_internal_addresses_are_not_public(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["93.184.215.14", "::ffff:8.8.8.8", "2606:4700::1111"])
def test_public_addresses_are_public(address):
    assert is_public(address)


@pytest.mark.parametrize(
    "url,code",
    [
        ("ftp://garden.example/", "url_scheme_unsupported"),
        ("file:///etc/passwd", "url_scheme_unsupported"),
        ("javascript:alert(1)", "url_scheme_unsupported"),
        ("https://user:secret@garden.example/", "url_credentials"),
        ("https://garden.example:8443/", "url_port_unsupported"),
        ("http://127.0.0.1/", "url_blocked_address"),
        ("http://[::1]/", "url_blocked_address"),
        ("http://169.254.169.254/latest/meta-data/", "url_blocked_address"),
        ("http://localhost/", "url_blocked_address"),
        ("http://printer.local/", "url_blocked_address"),
        ("https://garden.example/a b", "url_invalid"),
        ("https:///path", "url_invalid"),
        ("https://garden.example/" + "a" * 2048, "url_invalid"),
        ("", "url_invalid"),
    ],
)
def test_url_form_is_checked_before_any_network_use(url, code):
    with pytest.raises(FetchError) as raised:
        normalize_url(url)
    assert raised.value.code == code


def test_normalized_url_drops_the_fragment_and_case():
    assert normalize_url(" HTTPS://Garden.Example:443/Hours?x=1#top ") == (
        "https://garden.example/Hours?x=1"
    )
    assert fallback_title("https://garden.example/") == "garden.example"
    assert fallback_title("https://garden.example/hours") == "garden.example/hours"


def test_fetch_connects_to_the_checked_address_with_host_and_sni(web):
    _, sent = web
    assert fetch_page("https://garden.example/hours#top") == PAGE
    [request] = sent
    assert request.url.host == "93.184.215.14"
    assert request.url.path == "/hours"
    assert request.headers["host"] == "garden.example"
    assert request.extensions["sni_hostname"] == "garden.example"


def test_ipv6_answers_are_pinned_too(web):
    _, sent = web
    fetch_page("https://cdn.example/")
    assert sent[0].url.host == "2606:4700::1111"


def test_any_internal_answer_blocks_the_host(web, monkeypatch):
    _, sent = web
    DNS["mixed.example"] = ["93.184.215.14", "10.0.0.5"]
    try:
        with pytest.raises(FetchError, match="url_blocked_address"):
            fetch_page("https://mixed.example/")
    finally:
        del DNS["mixed.example"]
    assert sent == []


def test_redirect_to_an_internal_address_is_blocked(web):
    state, sent = web
    state["handler"] = lambda request: response(
        302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
    )
    with pytest.raises(FetchError, match="url_blocked_address"):
        fetch_page("https://garden.example/")
    assert len(sent) == 1


def test_redirect_to_a_name_that_resolves_inside_is_blocked(web):
    state, sent = web
    DNS["rebind.example"] = ["127.0.0.1"]
    state["handler"] = lambda request: response(
        301, headers={"location": "https://rebind.example/"}
    )
    try:
        with pytest.raises(FetchError, match="url_blocked_address"):
            fetch_page("https://garden.example/")
    finally:
        del DNS["rebind.example"]
    assert len(sent) == 1


def test_relative_redirects_are_followed_and_limited(web):
    state, sent = web

    def handler(request):
        if request.url.path == "/final":
            return response(200, headers=HTML, content=PAGE)
        return response(307, headers={"location": "/final"})

    state["handler"] = handler
    assert fetch_page("https://garden.example/start") == PAGE
    assert [r.url.path for r in sent] == ["/start", "/final"]
    assert sent[1].headers["host"] == "garden.example"

    sent.clear()
    state["handler"] = lambda request: response(302, headers={"location": "/again"})
    with pytest.raises(FetchError, match="url_too_many_redirects"):
        fetch_page("https://garden.example/")
    assert len(sent) == web_fetch.MAX_REDIRECTS + 1


@pytest.mark.parametrize(
    "reply,code",
    [
        (response(404, headers=HTML, content=PAGE), "url_http_error"),
        (response(302), "url_http_error"),
        (response(200, headers={"content-type": "application/pdf"}), "url_unsupported_type"),
        (response(200, headers={"content-type": "image/png"}), "url_unsupported_type"),
        (response(200, content=PAGE), "url_unsupported_type"),
        (
            response(200, headers={**HTML, "content-encoding": "br"}, content=PAGE),
            "url_unsupported_type",
        ),
        (
            response(200, headers={**HTML, "content-encoding": "gzip"}, content=b"bad"),
            "url_fetch_failed",
        ),
    ],
)
def test_unusable_responses_have_actionable_codes(web, reply, code):
    state, _ = web
    state["handler"] = lambda request: reply
    with pytest.raises(FetchError) as raised:
        fetch_page("https://garden.example/")
    assert raised.value.code == code


def test_size_limit_applies_to_declared_streamed_and_decompressed_bodies(web, monkeypatch):
    state, _ = web
    monkeypatch.setattr(get_settings(), "upload_max_bytes", 1024)
    big = b"<p>" + b"x" * 2000 + b"</p>"
    for headers, content in [
        (HTML, big),
        ({**HTML, "content-encoding": "gzip"}, gzip.compress(big)),
    ]:
        state["handler"] = lambda request, h=headers, c=content: response(200, headers=h, content=c)
        with pytest.raises(FetchError, match="url_too_large"):
            fetch_page("https://garden.example/")
    small = gzip.compress(PAGE)
    state["handler"] = lambda request: response(
        200, headers={**HTML, "content-encoding": "gzip"}, content=small
    )
    assert fetch_page("https://garden.example/") == PAGE


def test_timeouts_and_connection_errors(web):
    state, _ = web

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    state["handler"] = slow
    with pytest.raises(FetchError, match="url_timeout"):
        fetch_page("https://garden.example/")

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    state["handler"] = refused
    with pytest.raises(FetchError, match="url_fetch_failed"):
        fetch_page("https://garden.example/")


def test_unknown_names_fail_as_dns_errors(web):
    with pytest.raises(FetchError, match="url_dns_failed"):
        fetch_page("https://missing.example/")


def test_real_resolver_errors_map_to_dns_failure():
    with (
        patch("socket.getaddrinfo", side_effect=socket.gaierror("no name")),
        pytest.raises(FetchError, match="url_dns_failed"),
    ):
        web_fetch.resolve("missing.example")


def test_the_real_client_ignores_environment_proxies(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    with web_fetch.open_client() as client:
        assert client._trust_env is False
        assert client.follow_redirects is False
