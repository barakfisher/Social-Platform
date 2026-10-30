"""Fetch an owner-submitted public web page without reaching internal services (SP-9).

Every hop is checked before connecting: http(s) only, default ports, no credentials, and
every address the host resolves to must be public. The connection then goes to the
checked address (Host header and TLS SNI keep the name), so a second DNS answer cannot
point it elsewhere. Redirects are followed by hand and checked the same way. Environment
proxies are ignored: a proxy would resolve the name itself.
"""

import ipaddress
import socket
import time
import zlib

import httpx

from app.config import get_settings

MAX_URL_LENGTH = 2048
MAX_REDIRECTS = 3
TOTAL_SECONDS = 30
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
REDIRECTS = frozenset({301, 302, 303, 307, 308})
NAT64 = ipaddress.ip_network("64:ff9b::/96")
USER_AGENT = "SocialPlatform-KnowledgeBase/0.1 (owner-submitted source)"


class FetchError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.teredo:
            return False
        # Addresses that carry an IPv4 address inside must pass as that address.
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour:
            ip = ip.sixtofour
        elif ip in NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


def ip_literal(host: str) -> str | None:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def normalize_url(raw: str) -> str:
    """Checks that need no network; returns the URL without its fragment."""
    raw = raw.strip()
    if not raw or len(raw) > MAX_URL_LENGTH or any(c.isspace() or ord(c) < 32 for c in raw):
        raise FetchError("url_invalid")
    try:
        url = httpx.URL(raw)
        host = url.raw_host.decode("ascii").lower()
    except (httpx.InvalidURL, UnicodeError, ValueError):
        raise FetchError("url_invalid") from None
    if url.scheme not in ("http", "https"):
        raise FetchError("url_scheme_unsupported")
    if url.userinfo:
        raise FetchError("url_credentials")
    if not host:
        raise FetchError("url_invalid")
    if url.port not in (None, 80, 443):
        raise FetchError("url_port_unsupported")
    literal = ip_literal(host)
    if literal is not None and not is_public(literal):
        raise FetchError("url_blocked_address")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchError("url_blocked_address")
    return str(url.copy_with(fragment=None))


def fallback_title(url: str) -> str:
    """Host and path, shown until the page's own title is known."""
    parsed = httpx.URL(url)
    return (parsed.host + (parsed.path if parsed.path != "/" else ""))[:300]


def resolve(host: str) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise FetchError("url_dns_failed") from None
    return list(dict.fromkeys(str(answer[4][0]) for answer in answers))


def open_client() -> httpx.Client:
    return httpx.Client(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(10, connect=5),
    )


def read_body(response: httpx.Response, limit: int, deadline: float) -> bytes:
    # Raw bytes with our own bounded decoder: a small gzip body cannot inflate past the limit.
    encoding = (response.headers.get("content-encoding") or "identity").strip().lower()
    if encoding in ("gzip", "x-gzip"):
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif encoding == "deflate":
        decoder = zlib.decompressobj()
    elif encoding == "identity":
        decoder = None
    else:
        raise FetchError("url_unsupported_type")
    body = bytearray()
    try:
        for chunk in response.iter_raw():
            if time.monotonic() > deadline:
                raise FetchError("url_timeout")
            if decoder is None:
                body.extend(chunk)
            else:
                body.extend(decoder.decompress(chunk, limit + 1 - len(body)))
                if decoder.unconsumed_tail:
                    raise FetchError("url_too_large")
            if len(body) > limit:
                raise FetchError("url_too_large")
    except zlib.error:
        raise FetchError("url_fetch_failed") from None
    return bytes(body)


def fetch_page(raw_url: str) -> bytes:
    """The HTML of a public page, or FetchError with an actionable code."""
    limit = get_settings().upload_max_bytes
    deadline = time.monotonic() + TOTAL_SECONDS
    current = normalize_url(raw_url)
    with open_client() as client:
        for _ in range(MAX_REDIRECTS + 1):
            target = httpx.URL(current)
            host = target.raw_host.decode("ascii").lower()
            literal = ip_literal(host)
            addresses = [literal] if literal else resolve(host)
            if not addresses or not all(is_public(address) for address in addresses):
                raise FetchError("url_blocked_address")
            extensions = {"sni_hostname": host} if target.scheme == "https" else {}
            try:
                with client.stream(
                    "GET",
                    target.copy_with(host=addresses[0]),
                    headers={
                        "Host": target.netloc.decode("ascii"),
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Encoding": "gzip, deflate, identity",
                    },
                    extensions=extensions,
                ) as response:
                    if response.status_code in REDIRECTS:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("url_http_error")
                        current = normalize_url(str(target.join(location)))
                        continue
                    if not 200 <= response.status_code < 300:
                        raise FetchError("url_http_error")
                    content_type = response.headers.get("content-type", "")
                    if content_type.split(";")[0].strip().lower() not in HTML_TYPES:
                        raise FetchError("url_unsupported_type")
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > limit:
                        raise FetchError("url_too_large")
                    return read_body(response, limit, deadline)
            except httpx.TimeoutException:
                raise FetchError("url_timeout") from None
            except httpx.HTTPError:
                raise FetchError("url_fetch_failed") from None
    raise FetchError("url_too_many_redirects")
