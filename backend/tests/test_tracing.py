import json
from unittest.mock import patch

import httpx
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr

from app import tracing
from app.generation_provider import GenerationError, chat_completion
from app.local_scope import LOCAL_USER_ID
from tests.test_generation import (  # noqa: F401 (fixtures)
    catalog,
    payload,
    provider,
    service_api,
    settings,
    setup_brand,
    setup_source,
)

PROVIDER_KEY = "sk-or-test-never-traced"
# One recording client for the module: the SDK keeps a single client per public key.
EXPORTER = InMemorySpanExporter()
RECORDER = Langfuse(
    public_key="pk-lf-test",
    secret_key="sk-lf-test",
    base_url="http://127.0.0.1:9",
    environment="test",
    span_exporter=EXPORTER,
)


@pytest.fixture
def spans(settings):  # noqa: F811
    """Tracing on, recorded in memory: nothing leaves the test."""
    settings.generation_api_key = SecretStr(PROVIDER_KEY)
    EXPORTER.clear()

    def finished():
        RECORDER.flush()
        return {span.name: span for span in EXPORTER.get_finished_spans()}

    with patch("app.tracing.tracer", return_value=RECORDER):
        yield finished
    EXPORTER.clear()


def attribute(span, name):
    """Langfuse stores structured values, metadata included, as JSON text."""
    value = span.attributes.get(f"langfuse.observation.{name}")
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def answer(content, config, cost=0.00002):
    return httpx.Response(
        200,
        json={
            "model": config.generation_model + "-2026-01-01",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10, "cost": cost},
        },
    )


@pytest.mark.parametrize(
    "public_key,secret_key,enabled",
    [("", "", False), ("pk-lf-x", "", False), ("", "sk-lf-x", False), ("pk-lf-x", "sk-lf-x", True)],
)
def test_tracing_is_on_only_with_both_keys(settings, public_key, secret_key, enabled):  # noqa: F811
    settings.langfuse_public_key = public_key
    settings.langfuse_secret_key = SecretStr(secret_key)
    tracing.tracer.cache_clear()
    with patch("app.tracing.Langfuse") as langfuse:
        tracing.tracer()
    options = langfuse.call_args.kwargs
    assert options["tracing_enabled"] is enabled
    assert options["base_url"] == settings.langfuse_base_url
    assert options["environment"] == settings.environment


def test_untraced_calls_work_as_before(provider, settings):  # noqa: F811
    """Without keys (conftest), a call returns what it always did and nothing is recorded."""
    assert tracing.tracer()._tracing_enabled is False
    with provider(
        lambda r: (
            httpx.Response(200, json=catalog()) if r.method == "GET" else answer("{}", settings)
        )
    ):
        content, metadata = chat_completion("system", "user", 100)
    assert content == "{}" and metadata["attempts"] == 1


def test_model_call_is_a_generation_without_the_key(provider, settings, spans):  # noqa: F811
    """Usage, OpenRouter's cost and the answering model; the provider key never appears."""

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=catalog())
        return answer('{"content": "Draft"}', settings)

    with provider(handler):
        chat_completion("system text", "user text", 100, name="write-draft")
    generation = spans()["write-draft"]
    assert attribute(generation, "type") == "generation"
    assert attribute(generation, "input") == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]
    assert attribute(generation, "output") == {"content": "Draft"}
    # The model that answered, not only the one requested.
    assert attribute(generation, "model.name") == settings.generation_model + "-2026-01-01"
    assert attribute(generation, "model.parameters") == {
        "temperature": 0,
        "max_completion_tokens": settings.generation_max_output_tokens,
    }
    assert attribute(generation, "usage_details") == {"input": 50, "output": 10}
    assert attribute(generation, "cost_details") == {"total": 0.00002}
    assert attribute(generation, "metadata.requested_model") == settings.generation_model
    recorded = json.dumps(dict(generation.attributes))
    assert PROVIDER_KEY not in recorded and "Authorization" not in recorded


def test_failed_model_call_is_recorded_as_an_error(provider, settings, spans):  # noqa: F811
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=catalog())
        return httpx.Response(402)

    with provider(handler), pytest.raises(GenerationError):
        chat_completion("system", "user", 100, name="review-draft")
    generation = spans()["review-draft"]
    assert attribute(generation, "level") == "ERROR"
    assert attribute(generation, "status_message") == "generation_payment_required"
    recorded = json.dumps(
        [dict(generation.attributes), str(generation.status.description)]
        + [[event.name, dict(event.attributes or {})] for event in generation.events]
    )
    assert PROVIDER_KEY not in recorded and "Authorization" not in recorded


def test_draft_and_its_check_share_a_session(service_api, provider, settings, spans):  # noqa: F811
    """A draft is one trace with its steps nested; its source check is another trace."""
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=catalog())
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        chunk_id = data["sources"][0]["chunk_id"]
        draft = {"content": "Rosemary grows here.", "source_ids": [chunk_id], "warnings": []}
        return answer(json.dumps(draft), settings)

    with provider(handler):
        generation.side_effect = chat_completion
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    run_id = response.json()["id"]
    with patch("app.recheck.check_draft", return_value={"status": "checked", "findings": []}):
        assert client.post(f"/generation/{run_id}/review", json={}).status_code == 200

    recorded = spans()
    root, check = recorded["generate-draft"], recorded["check-sources"]
    # FastAPI's own request spans are not exported; Langfuse shows each action as the root
    # of its own trace.
    for action in (root, check):
        assert action.attributes["langfuse.internal.is_app_root"] is True
    assert root.context.trace_id != check.context.trace_id
    for name, kind in [
        ("embed-topic", "embedding"),
        ("retrieve-sources", "retriever"),
        ("write-draft", "generation"),
        ("find-restated-sentences", "guardrail"),
    ]:
        assert recorded[name].parent.span_id == root.context.span_id, name
        assert attribute(recorded[name], "type") == kind
    assert attribute(root, "input")["topic"] == payload()["topic"]
    assert attribute(root, "output")["content"] == "Rosemary grows here."
    sources = attribute(recorded["retrieve-sources"], "output")
    assert [s["title"] for s in sources] == ["Source"] and "content" not in sources[0]
    for span in (root, recorded["write-draft"], check):
        assert span.attributes["user.id"] == str(LOCAL_USER_ID)
        assert span.attributes["session.id"] == run_id


def test_failed_draft_marks_its_trace_as_an_error(service_api, spans):  # noqa: F811
    client, factory, _, _ = service_api
    setup_brand(factory)
    assert client.post("/generation", json=payload()).status_code == 409
    root = spans()["generate-draft"]
    assert attribute(root, "level") == "ERROR"
    assert attribute(root, "status_message") == "insufficient_context"


def test_a_tracing_failure_never_costs_a_paid_draft(service_api, provider, settings, spans):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=catalog())
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        draft = {"content": "Rosemary.", "source_ids": [data["sources"][0]["chunk_id"]]}
        return answer(json.dumps({**draft, "warnings": []}), settings)

    with (
        provider(handler),
        patch(
            "langfuse._client.span.LangfuseObservationWrapper.update",
            side_effect=RuntimeError("tracing broke"),
        ),
    ):
        generation.side_effect = chat_completion
        response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["content"] == "Rosemary."


def test_a_bad_langfuse_setting_turns_tracing_off(provider, settings, monkeypatch):  # noqa: F811
    """A malformed LANGFUSE_* environment value must not fail the call it would trace."""
    settings.langfuse_public_key = "pk-lf-x"
    settings.langfuse_secret_key = SecretStr("sk-lf-x")
    monkeypatch.setenv("LANGFUSE_SAMPLE_RATE", "not-a-number")
    tracing.tracer.cache_clear()
    with provider(
        lambda r: (
            httpx.Response(200, json=catalog()) if r.method == "GET" else answer("{}", settings)
        )
    ):
        assert chat_completion("system", "user", 100)[0] == "{}"
