"""Private storage for uploaded source files (SP-9): local disk behind opaque keys.

Keys are random and never derived from user input, so a filename cannot choose a path.
Files are written owner-only and replaced atomically; the API never serves them back.
"""

import os
import re
import secrets
from pathlib import Path

from app.config import get_settings

KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class StorageError(Exception):
    pass


def root() -> Path:
    path = Path(get_settings().source_storage_dir)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def object_path(key: str) -> Path:
    if not KEY_PATTERN.fullmatch(key):
        raise StorageError("invalid_storage_key")
    return root() / key


def put(data: bytes) -> str:
    key = secrets.token_hex(16)
    path = object_path(key)
    temporary = path.with_name(f".{key}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StorageError("storage_failed") from exc
    return key


def read(key: str) -> bytes:
    try:
        return object_path(key).read_bytes()
    except FileNotFoundError as exc:
        raise StorageError("source_file_missing") from exc
    except OSError as exc:
        raise StorageError("storage_failed") from exc


def remove(key: str) -> None:
    object_path(key).unlink(missing_ok=True)
