import os
from decimal import Decimal

import pytest

from app.config import Settings
from app.generation import TRANSLATION_BUDGET_SHARE
from app.generation_provider import attempt_estimate_usd

# OpenRouter catalog pricing (USD per token) for the default writer and every reviewer
# model users may choose. Update alongside the defaults or GENERATION_REVIEW_MODELS.
DEFAULT_MODEL_PRICING = {
    "openai/gpt-4.1": {
        "prompt_price": Decimal("0.000002"),
        "completion_price": Decimal("0.000008"),
    },
    "openai/gpt-5.6-terra": {
        "prompt_price": Decimal("0.000002"),
        "completion_price": Decimal("0.000012"),
    },
}


@pytest.fixture
def defaults(monkeypatch):
    # Code defaults only: no .env file and no inherited GENERATION_* overrides.
    for name in list(os.environ):
        if name.startswith("GENERATION_"):
            monkeypatch.delenv(name)
    return Settings(_env_file=None)


def smallest_stage_budget(settings: Settings) -> Decimal:
    cap = Decimal(str(settings.generation_max_request_usd))
    return cap * (1 - Decimal(str(TRANSLATION_BUDGET_SHARE))) / 2


def stage_models(settings: Settings) -> list[tuple[str, int]]:
    return [(settings.generation_model, settings.generation_max_output_tokens)] + [
        (model, settings.generation_review_max_output_tokens)
        for model in settings.generation_review_models
    ]


def test_default_budget_affords_largest_allowed_prompt(defaults):
    # Any prompt that passes the prompt-budget guard must also pass the spending preflight,
    # even after the translation fallback reserves its share, for the writer and for every
    # reviewer a user may choose. Otherwise a full source context fails with
    # generation_spending_limit.
    for model_id, output_limit in stage_models(defaults):
        model = DEFAULT_MODEL_PRICING[model_id]
        worst_case = attempt_estimate_usd(
            defaults.generation_prompt_budget, output_limit, model
        ) * (defaults.generation_retries + 1)
        assert worst_case <= smallest_stage_budget(defaults), model_id


def test_default_context_budget_fits_inside_prompt_budget(defaults):
    assert defaults.generation_context_budget < defaults.generation_prompt_budget
