import os
from decimal import Decimal

import pytest

from app.config import Settings
from app.generation import TRANSLATION_BUDGET_SHARE
from app.generation_provider import attempt_estimate_usd
from app.writer_models import WRITER_PROFILES, provider_tokens

# OpenRouter catalog pricing (USD per token) for every writer and reviewer model users may
# choose. Update alongside GENERATION_WRITER_MODELS or GENERATION_REVIEW_MODELS.
DEFAULT_MODEL_PRICING = {
    "openai/gpt-4.1": {
        "prompt_price": Decimal("0.000002"),
        "completion_price": Decimal("0.000008"),
    },
    "openai/gpt-5.6-terra": {
        "prompt_price": Decimal("0.000002"),
        "completion_price": Decimal("0.000012"),
    },
    "google/gemini-3.8-flash": {
        "prompt_price": Decimal("0.000000825"),
        "completion_price": Decimal("0.000004125"),
    },
    "anthropic/claude-opus-5.5": {
        "prompt_price": Decimal("0.000004"),
        "completion_price": Decimal("0.00002"),
    },
    "openai/gpt-5.6-sol": {
        "prompt_price": Decimal("0.000004"),
        "completion_price": Decimal("0.00002"),
    },
}


@pytest.fixture
def defaults(monkeypatch):
    # Code defaults only: no .env file and no inherited GENERATION_* overrides.
    for name in list(os.environ):
        if name.startswith("GENERATION_"):
            monkeypatch.delenv(name)
    return Settings(_env_file=None)


def stage_models(settings: Settings) -> list[tuple[str, int, int, Decimal]]:
    """(model, worst-case provider prompt tokens, output limit, smallest allowance) for every
    choosable stage. The writer is a draft's only paid stage, left with the cap after the
    translation fallback's share; the source check runs on request with the whole cap."""
    cap = Decimal(str(settings.generation_max_request_usd))
    writers = [
        (
            model,
            provider_tokens(settings.generation_prompt_budget, WRITER_PROFILES[model]),
            WRITER_PROFILES[model].output_tokens or settings.generation_max_output_tokens,
            cap * (1 - Decimal(str(TRANSLATION_BUDGET_SHARE))),
        )
        for model in settings.generation_writer_models
    ]
    return writers + [
        (
            model,
            settings.generation_prompt_budget,
            settings.generation_review_max_output_tokens,
            cap,
        )
        for model in settings.generation_review_models
    ]


def test_default_budget_affords_largest_allowed_prompt(defaults):
    # Any prompt that passes the prompt-budget guard must also pass the spending preflight,
    # even after the translation fallback reserves its share, for every writer (at its own
    # token ratio and output limit) and every reviewer a user may choose. Otherwise a full
    # source context fails with generation_spending_limit.
    for model_id, prompt_tokens, output_limit, allowance in stage_models(defaults):
        model = DEFAULT_MODEL_PRICING[model_id]
        worst_case = attempt_estimate_usd(prompt_tokens, output_limit, model) * (
            defaults.generation_retries + 1
        )
        assert worst_case <= allowance, model_id


def test_default_context_budget_fits_inside_prompt_budget(defaults):
    assert defaults.generation_context_budget < defaults.generation_prompt_budget
