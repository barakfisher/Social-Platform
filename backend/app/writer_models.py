"""Writer models a user may choose per draft, with measured token ratios and cost estimates."""

import math
from dataclasses import dataclass
from decimal import Decimal

from app.config import get_settings
from app.generation_provider import GenerationError, attempt_estimate_usd, model_details


@dataclass(frozen=True)
class WriterProfile:
    # Provider-reported prompt tokens per o200k_base token on long source text, the larger of
    # EN and HE, rounded up. Budgets stay in o200k units; costs and the context-length check
    # use the scaled count (docs/implementation.md, SP-22 tokenizer decision).
    token_ratio: Decimal
    # Provider-reported prompt/completion tokens of one realistic draft. Typical cost = these
    # tokens x the model's live price. Remeasure when the writer prompt changes.
    typical_tokens: tuple[int, int]
    # Room for reasoning writers; None uses GENERATION_MAX_OUTPUT_TOKENS.
    output_tokens: int | None = None

    def __post_init__(self):
        # A float or zero ratio would silently misreserve; fail when the module loads.
        if not (
            isinstance(self.token_ratio, Decimal)
            and self.token_ratio.is_finite()
            and self.token_ratio > 0
        ):
            raise ValueError("token_ratio must be a positive finite Decimal")
        if min(self.typical_tokens) < 0 or (
            self.output_tokens is not None and self.output_tokens < 1
        ):
            raise ValueError("token counts must be positive")


# Only measured writers have a profile; a listed writer without one cannot be chosen.
# GPT-4.1: o200k counts match within a constant 29 tokens; typical tokens from a stored
# Hebrew LinkedIn run (2,447 prompt / 251 completion, 2026-10-27).
WRITER_PROFILES = {
    "openai/gpt-4.1": WriterProfile(token_ratio=Decimal("1.0"), typical_tokens=(2447, 251)),
}


def writer_profile(model_id: str) -> WriterProfile:
    settings = get_settings()
    profile = WRITER_PROFILES.get(model_id)
    if model_id not in settings.generation_writer_models or profile is None:
        raise GenerationError("writer_model_unavailable")
    return profile


def provider_tokens(o200k_tokens: int, profile: WriterProfile) -> int:
    """Estimated provider-side prompt tokens for a count made with o200k_base."""
    return math.ceil(Decimal(o200k_tokens) * profile.token_ratio)


def writer_output_tokens(profile: WriterProfile) -> int:
    return profile.output_tokens or get_settings().generation_max_output_tokens


def writer_model_options() -> dict:
    settings = get_settings()
    options = []
    for model_id in settings.generation_writer_models:
        try:
            profile = writer_profile(model_id)
            model = model_details(model_id)
        except GenerationError:
            # Unmeasured, unpriced or delisted writers stay visible but cannot be chosen.
            options.append(
                {"id": model_id, "available": False, "typical_usd": None, "max_usd": None}
            )
            continue
        prompt, completion = profile.typical_tokens
        typical = prompt * model["prompt_price"] + completion * model["completion_price"]
        # The worst case the server reserves before calling: largest admitted prompt, scaled
        # to the provider's tokenizer, full output limit and every retry.
        maximum = attempt_estimate_usd(
            provider_tokens(settings.generation_prompt_budget, profile),
            writer_output_tokens(profile),
            model,
        ) * (settings.generation_retries + 1)
        options.append(
            {
                "id": model_id,
                "available": True,
                "typical_usd": float(typical),
                "max_usd": float(maximum),
            }
        )
    return {"default": settings.generation_model, "models": options}
