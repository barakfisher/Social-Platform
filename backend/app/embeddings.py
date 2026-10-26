import hashlib
import json
import math
from contextlib import contextmanager
from uuid import UUID

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.db import engine


class EmbeddingError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class TransientEmbeddingError(EmbeddingError):
    pass


def configured() -> bool:
    return bool(get_settings().embedding_api_key.get_secret_value().strip())


def profile_key() -> str:
    settings = get_settings()
    values = [
        settings.embedding_base_url.rstrip("/"),
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedding_revision,
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def embed_texts(inputs: list[str]) -> list[list[float]]:
    settings = get_settings()
    if not configured():
        raise EmbeddingError("embedding_not_configured")
    if not inputs or len(inputs) > settings.embedding_batch_size:
        raise EmbeddingError("embedding_invalid_batch")
    try:
        with httpx.Client(timeout=settings.embedding_timeout, follow_redirects=False) as client:
            response = client.post(
                settings.embedding_base_url.rstrip("/") + "/embeddings",
                headers={
                    "Authorization": "Bearer " + settings.embedding_api_key.get_secret_value()
                },
                json={
                    "model": settings.embedding_model,
                    "input": inputs,
                    "dimensions": settings.embedding_dimensions,
                    "encoding_format": "float",
                },
            )
    except httpx.TransportError:
        raise TransientEmbeddingError("embedding_unavailable") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise TransientEmbeddingError(
            "embedding_rate_limited" if response.status_code == 429 else "embedding_unavailable"
        )
    if response.status_code in (401, 403):
        raise EmbeddingError("embedding_authentication_failed")
    if response.status_code == 402:
        raise EmbeddingError("embedding_payment_required")
    if response.status_code != 200:
        raise EmbeddingError("embedding_request_rejected")
    try:
        payload = response.json()
        allowed_models = {settings.embedding_model}
        # OpenRouter's OpenAI route returns the upstream identifier without its vendor prefix.
        if settings.embedding_base_url.rstrip(
            "/"
        ) == "https://openrouter.ai/api/v1" and settings.embedding_model.startswith("openai/"):
            allowed_models.add(settings.embedding_model.removeprefix("openai/"))
        if payload.get("model") not in allowed_models:
            raise ValueError()
        data = payload["data"]
        if not isinstance(data, list) or len(data) != len(inputs):
            raise ValueError()
        results: dict[int, list[float]] = {}
        for entry in data:
            index = entry["index"]
            vector = entry["embedding"]
            if type(index) is not int or not 0 <= index < len(inputs) or index in results:
                raise ValueError()
            if not isinstance(vector, list) or len(vector) != settings.embedding_dimensions:
                raise ValueError()
            if any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 3e38 for v in vector
            ):
                raise ValueError()
            floats = [float(v) for v in vector]
            if not math.hypot(*floats) > 0:
                raise ValueError()
            results[index] = floats
        return [results[i] for i in range(len(inputs))]
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise EmbeddingError("embedding_invalid_response") from None


@contextmanager
def embedding_lock(job_id: str):
    """Session advisory lock spans HTTP calls without holding row locks or a transaction."""
    key = int.from_bytes(UUID(job_id).bytes[:8], "big", signed=True)
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        connection.commit()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    connection.commit()
                except Exception:
                    connection.invalidate()
