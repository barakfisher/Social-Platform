"""Text extraction from uploaded source files (SP-8). Failures carry actionable codes."""

import re
from bisect import bisect_right
from io import BytesIO

import trafilatura
from billiard.exceptions import SoftTimeLimitExceeded
from pypdf import PdfReader

from app.chunking import normalize_text
from app.config import get_settings

PAGE_SEPARATOR = "\n\n"
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class ExtractionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def decode_text_file(data: bytes) -> str:
    """Strict UTF-8 (an optional BOM is dropped), normalized like pasted text."""
    if data.startswith(b"%PDF-"):
        raise ExtractionError("file_signature_mismatch")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractionError("file_not_utf8") from None
    if "\x00" in text:
        raise ExtractionError("file_not_text")
    text = normalize_text(text)
    if not text:
        raise ExtractionError("source_empty")
    if len(text) > get_settings().source_max_characters:
        raise ExtractionError("source_too_long")
    return text


def extract_pdf(data: bytes) -> tuple[str, list[tuple[int, int]]]:
    """Normalized text of every page that has text, joined by blank lines, and
    (character offset, 1-based page number) where each of those pages starts.

    Scanned pages have no text layer; OCR is not attempted.
    """
    settings = get_settings()
    pages: list[tuple[int, int]] = []
    parts: list[str] = []
    position = 0
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            # Owner-password-only files open with an empty user password.
            try:
                decrypted = bool(reader.decrypt(""))
            except Exception:
                decrypted = False
            if not decrypted:
                raise ExtractionError("pdf_encrypted")
        if len(reader.pages) == 0:
            raise ExtractionError("source_empty")
        if len(reader.pages) > settings.pdf_max_pages:
            raise ExtractionError("pdf_too_many_pages")
        for number, page in enumerate(reader.pages, start=1):
            text = normalize_text(page.extract_text() or "")
            if not text:
                continue
            if parts:
                position += len(PAGE_SEPARATOR)
            pages.append((position, number))
            parts.append(text)
            position += len(text)
            if position > settings.source_max_characters:
                raise ExtractionError("source_too_long")
    except (ExtractionError, SoftTimeLimitExceeded):
        raise
    except Exception:
        # pypdf raises many types for malformed files; none of them is worth retrying.
        raise ExtractionError("pdf_corrupt") from None
    if not parts:
        raise ExtractionError("pdf_requires_ocr")
    return PAGE_SEPARATOR.join(parts), pages


def extract_html(data: bytes) -> tuple[str, str | None]:
    """Main text of a web page as Markdown (headings kept), and the page's title.

    trafilatura drops navigation, footers and comments; it detects the encoding itself.
    """
    try:
        text = trafilatura.extract(
            data,
            output_format="markdown",
            include_comments=False,
            include_images=False,
            favor_precision=True,
        )
        metadata = trafilatura.extract_metadata(data)
    except SoftTimeLimitExceeded:
        raise
    except Exception:
        raise ExtractionError("url_parse_failed") from None
    text = normalize_text(text or "")
    if not text:
        raise ExtractionError("url_no_content")
    if len(text) > get_settings().source_max_characters:
        raise ExtractionError("source_too_long")
    title = normalize_text(metadata.title or "") if metadata else ""
    title = CONTROL_CHARACTERS.sub(" ", title).strip()[:300]
    return text, title or None


def page_range(pages: list[tuple[int, int]], char_start: int, char_end: int) -> dict:
    """First and last page that a chunk's [char_start, char_end) span touches."""
    starts = [start for start, _ in pages]

    def page_at(offset: int) -> int:
        return pages[max(bisect_right(starts, offset) - 1, 0)][1]

    return {"page_start": page_at(char_start), "page_end": page_at(max(char_end - 1, char_start))}
