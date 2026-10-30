"""Cross-site write protection for the API itself (docs/implementation.md, SP-23).

The Next.js proxies guard their own routes, but FastAPI listens on 127.0.0.1:58073 and any
page the owner opens can send it a "simple" POST without a CORS preflight. CORS only hides
the response; the write still runs. Every write must therefore come from an allowed origin
or from a non-browser client (the proxy, curl, scripts), and carry a JSON body if any.
"""

from starlette.datastructures import Headers

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Sec-Fetch-Site values a browser sends for the page's own origin or a user-typed request.
# "same-site" is not here: every localhost port is the same site.
TRUSTED_FETCH_SITES = frozenset({"same-origin", "none"})


# Raw-byte uploads (SP-9). application/octet-stream is not a CORS-safelisted type, so a
# cross-site browser request still needs a preflight, which CORS refuses. Multipart form
# data is never accepted: any page can send it without a preflight.
OCTET_STREAM_PATHS = frozenset({("POST", "/knowledge/files")})


def is_json_content_type(value: str | None) -> bool:
    return value is not None and value.split(";")[0].strip().lower() == "application/json"


def media_type(value: str | None) -> str | None:
    return None if value is None else value.split(";")[0].strip().lower()


def has_body(headers: Headers) -> bool:
    return "transfer-encoding" in headers or headers.get("content-length", "0") != "0"


def write_rejection(
    method: str, headers: Headers, allowed_origins: list[str], path: str = ""
) -> tuple[int, str] | None:
    """(status, error code) for a write the API must refuse, or None to let it through.

    A write with neither Origin nor Sec-Fetch-Site comes from a non-browser client, which
    cannot ride the owner's browser, so it is allowed.
    """
    if method not in UNSAFE_METHODS:
        return None
    origin = headers.get("origin")
    fetch_site = headers.get("sec-fetch-site")
    allowed_origin = origin is not None and origin in allowed_origins
    if origin is not None and not allowed_origin:
        return 403, "cross_site_request"
    if fetch_site is not None and fetch_site not in TRUSTED_FETCH_SITES and not allowed_origin:
        return 403, "cross_site_request"
    content_type = media_type(headers.get("content-type"))
    if (method, path) in OCTET_STREAM_PATHS:
        if content_type != "application/octet-stream":
            return 415, "invalid_content_type"
    elif has_body(headers) and content_type != "application/json":
        return 415, "invalid_content_type"
    return None
