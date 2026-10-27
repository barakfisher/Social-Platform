"""Source-check models a user may choose per draft, with cost estimates from live prices."""

from app.config import get_settings
from app.generation_provider import GenerationError, attempt_estimate_usd, model_details

# Provider-reported prompt/completion tokens from one realistic Hebrew review (two retrieved
# chunks, source-review-v4, 2026-10-26); see verification/generation-grounding.md. Typical
# cost = these tokens x the model's live price. Remeasure when the review prompt changes.
TYPICAL_REVIEW_TOKENS = {
    "openai/gpt-5.6-terra": (2523, 907),
    "openai/gpt-4.1": (2021, 501),
}


def review_model_options() -> dict:
    settings = get_settings()
    options = []
    for model_id in settings.generation_review_models:
        try:
            model = model_details(model_id)
        except GenerationError:
            # Unpriced or delisted models stay visible but cannot be chosen.
            options.append(
                {"id": model_id, "available": False, "typical_usd": None, "max_usd": None}
            )
            continue
        tokens = TYPICAL_REVIEW_TOKENS.get(model_id)
        typical = (
            tokens[0] * model["prompt_price"] + tokens[1] * model["completion_price"]
            if tokens
            else None
        )
        # The worst case the server reserves before calling: largest admitted prompt, full
        # output limit and every retry.
        maximum = attempt_estimate_usd(
            settings.generation_prompt_budget, settings.generation_review_max_output_tokens, model
        ) * (settings.generation_retries + 1)
        options.append(
            {
                "id": model_id,
                "available": True,
                "typical_usd": float(typical) if typical is not None else None,
                "max_usd": float(maximum),
            }
        )
    return {"default": settings.generation_review_model, "models": options}
