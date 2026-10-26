import json
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.generation_provider import GenerationError
from app.query_translation import TRANSLATION_SYSTEM, translate_query


@pytest.mark.parametrize(
    "topic,query,target",
    [("garden rosemary", "רוזמרין בגינה", "he"), ("רוזמרין בגינה", "garden rosemary", "en")],
)
def test_translation_target_budget_and_data_isolation(topic, query, target):
    metadata = {"usage": {"cost_usd": 0.00001}, "estimated_max_usd": 0.0001, "attempts": 1}
    with patch(
        "app.query_translation.chat_completion",
        return_value=(json.dumps({"query": query}), metadata),
    ) as provider:
        result = translate_query(topic, budget_usd=0.001)
    assert result is not None
    assert result[0] == query
    assert result[1]["target_language"] == target
    assert result[1]["cost_usd"] == 0.00001
    system, user, _ = provider.call_args.args
    assert system == TRANSLATION_SYSTEM
    assert json.loads(user) == {"topic": topic, "target_language": target}
    assert provider.call_args.kwargs["budget_usd"] == 0.001
    assert provider.call_args.kwargs["model_id"] == get_settings().generation_model
    assert provider.call_args.kwargs["output_tokens"] <= 450


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "{}",
        "[]",
        '{"query": 4}',
        '{"query":""}',
        '{"query":"   "}',
        '{"query":"hello"}',
        '{"query":"גינה", "extra":true}',
        '{"query":"גינה\\u0000"}',
        json.dumps({"query": "א" * 1001}),
        "invalid",
    ],
)
def test_invalid_translations_fail_closed_with_usage(raw):
    metadata = {"usage": {"cost_usd": 0.00001}, "estimated_max_usd": 0.0001, "attempts": 1}
    with patch("app.query_translation.chat_completion", return_value=(raw, metadata)):
        with pytest.raises(GenerationError, match="generation_translation_invalid") as error:
            translate_query("hello", budget_usd=0.001)
    assert error.value.metadata == metadata


@pytest.mark.parametrize("topic", ["", " ", "12345", "!?", "你好"])
def test_unsupported_input_does_not_call_provider(topic):
    with patch("app.query_translation.chat_completion") as provider:
        assert translate_query(topic, budget_usd=0.001) is None
    provider.assert_not_called()


def test_translation_prompt_limit_prevents_provider_call():
    with (
        patch("app.query_translation.prompt_tokens", return_value=10**9),
        patch("app.query_translation.chat_completion") as provider,
    ):
        with pytest.raises(GenerationError, match="generation_prompt_limit"):
            translate_query("garden", budget_usd=0.001)
    provider.assert_not_called()


def test_provider_failure_is_preserved_without_retry():
    with patch(
        "app.query_translation.chat_completion",
        side_effect=GenerationError("generation_unavailable"),
    ) as provider:
        with pytest.raises(GenerationError, match="generation_unavailable"):
            translate_query("garden", budget_usd=0.001)
    provider.assert_called_once()


@pytest.mark.parametrize("attempts", [1, 2])
def test_completed_attempt_reservation_only_counts_actual_attempts(attempts):
    settings = get_settings().model_copy(deep=True)
    settings.generation_retries = 1
    metadata = {"estimated_max_usd": 0.0001, "attempts": attempts, "usage": {"cost_usd": 0.00001}}
    with (
        patch("app.query_translation.get_settings", return_value=settings),
        patch("app.query_translation.chat_completion", return_value=('{"query":"גינה"}', metadata)),
    ):
        result = translate_query("garden", budget_usd=0.001)
    assert result is not None
    assert result[2] == pytest.approx(0.0001 * attempts)
    assert result[1]["consumed_max_usd"] == result[2]


@pytest.mark.parametrize(
    "reservation",
    [
        {},
        {"estimated_max_usd": 0.001},
        {"attempts": 1},
        {"estimated_max_usd": -1.0, "attempts": 1},
        {"estimated_max_usd": float("nan"), "attempts": 1},
        {"estimated_max_usd": float("inf"), "attempts": 1},
        {"estimated_max_usd": "0.001", "attempts": 1},
        {"estimated_max_usd": 0.001, "attempts": 0},
        {"estimated_max_usd": 0.001, "attempts": 4},
        {"estimated_max_usd": 0.001, "attempts": True},
        {"estimated_max_usd": 0.001, "attempts": "1"},
    ],
)
def test_invalid_completed_reservation_fails_closed(reservation):
    metadata = {**reservation, "usage": {"cost_usd": 0.00001}}
    with patch(
        "app.query_translation.chat_completion", return_value=('{"query":"גינה"}', metadata)
    ):
        with pytest.raises(GenerationError, match="generation_translation_invalid") as error:
            translate_query("garden", budget_usd=0.001)
    assert error.value.metadata == metadata


@pytest.mark.parametrize(
    "attempts,estimate,retries", [(2, 0.0001, 0), (3, 0.0001, 1), (2, 0.0006, 1)]
)
def test_completed_reservation_cannot_exceed_stage_allocation_or_configured_attempts(
    attempts, estimate, retries
):
    settings = get_settings().model_copy(deep=True)
    settings.generation_retries = retries
    metadata = {"estimated_max_usd": estimate, "attempts": attempts, "usage": {"cost_usd": 0.00001}}
    with (
        patch("app.query_translation.get_settings", return_value=settings),
        patch("app.query_translation.chat_completion", return_value=('{"query":"גינה"}', metadata)),
    ):
        with pytest.raises(GenerationError, match="generation_spending_limit"):
            translate_query("garden", budget_usd=0.001)
