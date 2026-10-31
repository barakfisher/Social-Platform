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
# GPT-4.1: o200k counts match within a constant 29 tokens; typical tokens are the medians of
# six live Hebrew drafts on the owner's Knowledge Base after the writer began reading every
# relevant chunk (5,593-19,043 prompt / 202-345 completion, 2026-10-31).
# Gemini 3.8 Flash: ratio measured on long EN/HE text (up to 1.2, rounded up); typical tokens
# from a realistic Hebrew LinkedIn prompt (2,585 / 1,007 incl. 775 reasoning, 2026-10-28). It
# reasons before writing: up to 1,055 completion tokens on synthetic sources, but a live Hebrew
# draft from Wikipedia sources used all of 2,000 and was cut off (2026-10-28), so 4,000.
# Typical tokens re-measured on a live Hebrew medium draft reading every relevant chunk
# (18,236 / 3,271, 2026-10-31).
# Claude Opus 5.5: 1.67-1.71 on the owner's six Hebrew topics, 1.80-1.85 on short scenario
# prompts (the Claude 5.5 family measured 1.66 EN / 1.78 HE on long text), so 1.8. Typical
# tokens are the medians of those six drafts (14,570-29,127 / 1,225-2,368 incl. reasoning,
# 2026-10-31); 4,000 leaves room for a long post.
# GPT-5.6-sol: o200k counts match within a constant 27 tokens, as GPT-4.1. Typical tokens are
# the medians of the same six drafts (8,562-17,431 / 340-1,004 incl. reasoning, 2026-10-31).
WRITER_PROFILES = {
    "openai/gpt-4.1": WriterProfile(token_ratio=Decimal("1.0"), typical_tokens=(13886, 311)),
    "google/gemini-3.8-flash": WriterProfile(
        token_ratio=Decimal("1.25"), typical_tokens=(18236, 3271), output_tokens=4000
    ),
    "anthropic/claude-opus-5.5": WriterProfile(
        token_ratio=Decimal("1.8"), typical_tokens=(22252, 1683), output_tokens=4000
    ),
    "openai/gpt-5.6-sol": WriterProfile(
        token_ratio=Decimal("1.0"), typical_tokens=(13232, 596), output_tokens=3000
    ),
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
