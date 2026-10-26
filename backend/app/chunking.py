import unicodedata
from functools import lru_cache

import tiktoken


@lru_cache
def encoding():
    return tiktoken.get_encoding("cl100k_base")


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def token_count(value: str) -> int:
    return len(encoding().encode_ordinary(value))


def chunk_text(text: str, target: int = 800, overlap: int = 100) -> list[dict]:
    """Keep Unicode character boundaries and offsets into normalized source text."""
    if target < 8 or not 0 <= overlap < target // 2:
        raise ValueError("Invalid chunk settings")
    if not text.strip():
        raise ValueError("Empty source")
    chunks = []
    start = 0
    while start < len(text):
        low, high = start + 1, min(len(text), start + target * 8)
        end = low
        while low <= high:
            middle = (low + high) // 2
            if token_count(text[start:middle]) <= target:
                end, low = middle, middle + 1
            else:
                high = middle - 1
        if end < len(text):
            floor = start + (end - start) * 2 // 3
            for boundary in ("\n\n", "\n", ". ", " "):
                match = text.rfind(boundary, floor, end)
                if match >= floor:
                    end = match + len(boundary)
                    break
        content = text[start:end]
        chunks.append(
            {
                "content": content,
                "token_count": token_count(content),
                "source_location": {
                    "char_start": start,
                    "char_end": end,
                    "tokenizer": "cl100k_base",
                },
            }
        )
        if end == len(text):
            break
        # Keep a bounded suffix as overlap without splitting Unicode characters.
        low, high, next_start = start + 1, end, end
        while low <= high:
            middle = (low + high) // 2
            if token_count(text[middle:end]) <= overlap:
                next_start, high = middle, middle - 1
            else:
                low = middle + 1
        start = max(start + 1, next_start)
    return chunks
