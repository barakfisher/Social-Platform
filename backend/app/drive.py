"""Read Google Drive folders the owner shared with the service account (SP-30). Read-only.

The service account sees only what was shared with it, and asks for the read-only scope.
google-auth signs its token with the key file; every Drive call goes to one fixed host,
follows no redirects and ignores environment proxies. Folder and file IDs are checked
before they reach a URL or a query, and downloads stop at the upload size limit.
"""

import json
import re
import threading
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

import httpx
import requests
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request as TokenRequest
from google.oauth2 import service_account

from app.config import get_settings

API = "https://www.googleapis.com/drive/v3"
# The only token endpoint a key file may name.
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TIMEOUT_SECONDS = 30
PAGE_SIZE = 100
FOLDER_TYPE = "application/vnd.google-apps.folder"
GOOGLE_DOC_TYPE = "application/vnd.google-apps.document"
# Drive IDs are URL-safe base64-like strings; anything else never reaches a request.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
FOLDER_LINK = re.compile(
    r"^https://drive\.google\.com/(?:drive/(?:u/\d+/)?folders/|open\?id=)([A-Za-z0-9_-]+)"
)
# The same extensions an upload accepts (app/knowledge.py FILE_TYPES).
FILE_FORMS = {".pdf": "pdf", ".txt": "text", ".md": "text"}
# Reasons in a 403 body that mean "try later", not "not allowed".
RATE_LIMITED = {"rateLimitExceeded", "userRateLimitExceeded"}


class DriveError(Exception):
    def __init__(self, code: str, transient: bool = False):
        super().__init__(code)
        self.code = code
        # A transient failure is retried by the next sync and never deletes anything.
        self.transient = transient


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str

    @property
    def form(self) -> str | None:
        """doc, pdf or text; None for a file the Knowledge Base does not import."""
        if self.mime_type == GOOGLE_DOC_TYPE:
            return "doc"
        if self.mime_type.startswith("application/vnd.google-apps."):
            return None
        return FILE_FORMS.get(PurePosixPath(self.name.lower()).suffix)


def key_path() -> Path | None:
    value = get_settings().google_service_account_file
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_file() else None


def configured() -> bool:
    return key_path() is not None


def service_account_email() -> str | None:
    """The address the owner shares folders with; nothing else is read from the key here."""
    path = key_path()
    if path is None:
        return None
    try:
        email = json.loads(path.read_text("utf-8")).get("client_email")
    except (OSError, ValueError, AttributeError):
        return None
    return email if isinstance(email, str) else None


_credentials: dict[Path, service_account.Credentials] = {}
_credentials_lock = threading.Lock()


def access_token() -> str:
    path = key_path()
    if path is None:
        raise DriveError("drive_not_configured")
    with _credentials_lock:
        credentials = _credentials.get(path)
        if credentials is None:
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    str(path), scopes=SCOPES
                )
            except (OSError, ValueError, KeyError):
                raise DriveError("drive_key_invalid") from None
            if credentials._token_uri != TOKEN_URI:
                raise DriveError("drive_key_invalid")
            _credentials[path] = credentials
        if not credentials.valid:
            # Like Drive calls: no environment proxies, no redirects, a bounded wait.
            session = requests.Session()
            session.trust_env = False
            session.max_redirects = 0
            try:
                credentials.refresh(partial(TokenRequest(session), timeout=TIMEOUT_SECONDS))
            except (TransportError, requests.RequestException):
                raise DriveError("drive_unavailable", transient=True) from None
            except RefreshError:
                raise DriveError("drive_key_invalid") from None
        if not credentials.token:
            raise DriveError("drive_key_invalid")
        return str(credentials.token)


def folder_id(value: str) -> str:
    """A folder link from the address bar or Share dialog, or the bare ID."""
    value = value.strip()
    match = FOLDER_LINK.match(value)
    candidate = match.group(1) if match else value
    if not ID_PATTERN.fullmatch(candidate):
        raise DriveError("drive_folder_invalid")
    return candidate


def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False, trust_env=False)


def failure(response: httpx.Response, body: bytes) -> DriveError:
    if response.status_code == 401:
        return DriveError("drive_key_invalid")
    if response.status_code == 404:
        # Drive answers 404 for anything not shared with the service account.
        return DriveError("drive_not_shared")
    if response.status_code == 403:
        try:
            errors = json.loads(body)["error"]["errors"]
            reasons = {e.get("reason") for e in errors}
        except (ValueError, KeyError, TypeError, AttributeError):
            reasons = set()
        if reasons & RATE_LIMITED:
            return DriveError("drive_unavailable", transient=True)
        if "exportSizeLimitExceeded" in reasons:
            return DriveError("file_too_large")
        return DriveError("drive_not_shared")
    if response.status_code == 429 or response.status_code >= 500:
        return DriveError("drive_unavailable", transient=True)
    return DriveError("drive_request_failed")


def get(path: str, params: dict) -> bytes:
    limit = get_settings().upload_max_bytes
    headers = {"Authorization": f"Bearer {access_token()}"}
    try:
        with (
            http_client() as client,
            client.stream("GET", f"{API}/{path}", params=params, headers=headers) as response,
        ):
            body = bytearray()
            for part in response.iter_bytes():
                body.extend(part)
                if len(body) > limit:
                    raise DriveError("file_too_large")
            if response.status_code != 200:
                raise failure(response, bytes(body))
            return bytes(body)
    except httpx.HTTPError:
        raise DriveError("drive_unavailable", transient=True) from None


def get_json(path: str, params: dict) -> dict:
    try:
        data = json.loads(get(path, params))
    except ValueError:
        raise DriveError("drive_request_failed") from None
    if not isinstance(data, dict):
        raise DriveError("drive_request_failed")
    return data


def folder_name(drive_folder_id: str) -> str:
    """The folder's name; fails as drive_not_shared when the service account cannot see it."""
    data = get_json(
        f"files/{folder_id(drive_folder_id)}",
        {"fields": "id,name,mimeType", "supportsAllDrives": "true"},
    )
    if data.get("mimeType") != FOLDER_TYPE:
        raise DriveError("drive_not_a_folder")
    return str(data.get("name") or "")[:300]


def list_folder(drive_folder_id: str) -> list[DriveFile]:
    """Every file directly in the folder (subfolders included, not their contents)."""
    checked = folder_id(drive_folder_id)
    limit = get_settings().drive_max_files
    files: list[DriveFile] = []
    page_token = None
    while True:
        params = {
            # The ID is checked against ID_PATTERN, so it cannot close the quoted string.
            "q": f"'{checked}' in parents and trashed = false",
            "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,modifiedTime)",
            "pageSize": str(PAGE_SIZE),
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        data = get_json("files", params)
        items = data.get("files")
        # A listing that is not whole must never read as "these files left the folder".
        if not isinstance(items, list) or data.get("incompleteSearch"):
            raise DriveError("drive_request_failed", transient=True)
        for item in items:
            try:
                file = DriveFile(
                    id=str(item["id"]),
                    name=str(item.get("name") or ""),
                    mime_type=str(item.get("mimeType") or ""),
                    modified_time=str(item.get("modifiedTime") or ""),
                )
            except (KeyError, TypeError):
                raise DriveError("drive_request_failed") from None
            if not ID_PATTERN.fullmatch(file.id) or not 0 < len(file.modified_time) <= 40:
                raise DriveError("drive_request_failed")
            files.append(file)
            if len(files) > limit:
                raise DriveError("drive_folder_too_large")
        page_token = data.get("nextPageToken")
        if not page_token:
            return files


def download(file: DriveFile) -> bytes:
    """A Google Doc as plain text (UTF-8); any other file as its own bytes."""
    if not ID_PATTERN.fullmatch(file.id):
        raise DriveError("drive_request_failed")
    if file.form == "doc":
        return get(f"files/{file.id}/export", {"mimeType": "text/plain"})
    return get(f"files/{file.id}", {"alt": "media", "supportsAllDrives": "true"})
