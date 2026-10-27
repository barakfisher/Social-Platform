import math
import time
from decimal import Decimal, InvalidOperation

import httpx

from app.config import get_settings


class GenerationError(Exception):
    def __init__(self, code: str, metadata: dict | None = None):
        self.code = code
        self.metadata = metadata or {}
        super().__init__(code)


def generation_key() -> str:
    settings = get_settings()
    if settings.generation_api_key.get_secret_value().strip():
        return settings.generation_api_key.get_secret_value().strip()
    if (
        settings.generation_base_url.rstrip("/")
        == settings.embedding_base_url.rstrip("/")
        == "https://openrouter.ai/api/v1"
    ):
        return settings.embedding_api_key.get_secret_value().strip()
    return ""


def attempt_estimate_usd(prompt_tokens: int, output_tokens: int, model: dict) -> Decimal:
    """Worst-case cost of one completion attempt, before retries."""
    return (
        Decimal(prompt_tokens + 128) * model["prompt_price"]
        + Decimal(output_tokens) * model["completion_price"]
    )


def model_details(model_id: str | None = None) -> dict:
    settings = get_settings()
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(settings.generation_base_url.rstrip("/") + "/models")
        if response.status_code != 200:
            raise GenerationError("generation_catalog_unavailable")
        model = next(
            (
                entry
                for entry in response.json()["data"]
                if entry["id"] == (model_id or settings.generation_model)
            ),
            None,
        )
        if model is None:
            raise GenerationError("generation_model_unavailable")
        prompt = Decimal(str(model["pricing"]["prompt"]))
        completion = Decimal(str(model["pricing"]["completion"]))
        if not prompt.is_finite() or not completion.is_finite() or min(prompt, completion) < 0:
            raise ValueError()
        return {
            "prompt_price": prompt,
            "completion_price": completion,
            "context_length": int(model["context_length"]),
        }
    except GenerationError:
        raise
    except (httpx.TransportError, ValueError, KeyError, TypeError, InvalidOperation):
        raise GenerationError("generation_catalog_unavailable") from None


def chat_completion(
    system: str,
    user: str,
    prompt_tokens: int,
    *,
    schema: dict | None = None,
    budget_usd: float | None = None,
    output_tokens: int | None = None,
    model_id: str | None = None,
) -> tuple[str, dict]:
    settings = get_settings()
    key = generation_key()
    if not key:
        raise GenerationError("generation_not_configured")
    model_id = model_id or settings.generation_model
    model = model_details(model_id)
    # Callers default to the writer limit; only the reviewer asks for its larger limit.
    output_tokens = min(
        output_tokens or settings.generation_max_output_tokens,
        max(settings.generation_max_output_tokens, settings.generation_review_max_output_tokens),
    )
    budget_usd = min(
        budget_usd if budget_usd is not None else settings.generation_max_request_usd,
        settings.generation_max_request_usd,
    )
    if prompt_tokens + output_tokens > model["context_length"]:
        raise GenerationError("generation_context_limit")
    estimate = attempt_estimate_usd(prompt_tokens, output_tokens, model)
    if estimate * (settings.generation_retries + 1) > Decimal(str(budget_usd)):
        raise GenerationError("generation_spending_limit")
    schema = schema or {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "content": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content", "source_ids", "warnings"],
    }
    for attempt in range(settings.generation_retries + 1):
        try:
            with httpx.Client(
                timeout=settings.generation_timeout, follow_redirects=False
            ) as client:
                response = client.post(
                    settings.generation_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + key},
                    json={
                        "model": model_id,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_completion_tokens": output_tokens,
                        "temperature": 0,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "grounded_post",
                                "strict": True,
                                "schema": schema,
                            },
                        },
                    },
                )
        except httpx.TransportError:
            response = None
        transient = response is None or response.status_code == 429 or response.status_code >= 500
        if transient:
            if attempt < settings.generation_retries:
                time.sleep(min(2**attempt, 4))
                continue
            raise GenerationError("generation_unavailable", {"attempts": attempt + 1})
        assert response is not None
        if response.status_code in (401, 403):
            raise GenerationError("generation_authentication_failed")
        if response.status_code == 402:
            raise GenerationError("generation_payment_required")
        if response.status_code != 200:
            raise GenerationError("generation_request_rejected")
        try:
            data = response.json()
            choice = data["choices"][0]
            # The output limit ran out (reasoning tokens count against it): its own code, so
            # the cause is visible instead of a generic invalid response.
            if choice.get("finish_reason") == "length":
                raise GenerationError(
                    "generation_output_truncated",
                    {"attempts": attempt + 1, "output_tokens": output_tokens},
                )
            if choice.get("finish_reason") != "stop":
                raise ValueError()
            content = choice["message"]["content"]
            usage = data["usage"]
            if not isinstance(content, str) or not content.strip() or len(content) > 30000:
                raise ValueError()
            for field in ["prompt_tokens", "completion_tokens"]:
                if type(usage[field]) is not int or usage[field] < 0:
                    raise ValueError()
            cost = usage.get("cost")
            if cost is not None and (
                type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0
            ):
                raise ValueError()
            actual_model = data.get("model")
            if not isinstance(actual_model, str) or not actual_model:
                raise ValueError()
            return content, {
                "requested_model": model_id,
                "model": actual_model,
                "usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "cost_usd": cost,
                },
                "estimated_max_usd": float(estimate),
                "reserved_max_usd": float(estimate * (settings.generation_retries + 1)),
                "attempts": attempt + 1,
            }
        except (ValueError, KeyError, TypeError, IndexError):
            raise GenerationError("generation_invalid_response") from None
    raise GenerationError("generation_unavailable")
