import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InternalError

from app.embeddings import EmbeddingError
from app.generation import LENGTH_LIMITS, LENGTH_TARGET_MINIMUMS, length_target
from app.generation_provider import GenerationError
from scripts import measure_draft_quality as measure
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    fake_completion,
    payload,
    service_api,
    settings,
    setup_brand,
    setup_source,
)

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def source(chunk: str, document: str) -> dict:
    return {"chunk_id": chunk, "document_id": document}


def row(**values) -> dict:
    defaults = {
        "minimum": LENGTH_TARGET_MINIMUMS["medium"],
        "maximum": LENGTH_LIMITS["medium"],
        "content": "word " * 10,
        "warnings": [],
        "sources": [source("c1", "d1"), source("c2", "d1"), source("c3", "d2")],
        "cited_ids": ["c1", "c3", "unknown"],
        "review": {"status": "checked", "findings": []},
        "cost_usd": 0.01,
        "seconds": 1.26,
    }
    return measure.draft_row({"topic": "t" * 100, "length": "medium"}, **(defaults | values))


# Report computations


def test_each_topic_is_measured_once_on_its_latest_inputs_oldest_topic_first():
    runs = [
        (NOW, {"topic": "b", "length": "short"}),
        (NOW - timedelta(days=2), {"topic": "a", "length": "short"}),
        (NOW - timedelta(days=1), {"topic": "a", "length": "medium"}),
        (NOW - timedelta(days=3), {"topic": "b", "length": "long"}),
    ]
    assert measure.latest_inputs(runs) == [
        {"topic": "a", "length": "medium"},
        {"topic": "b", "length": "short"},
    ]
    assert measure.latest_inputs([]) == []
    tied = [(NOW, {"topic": "b"}), (NOW, {"topic": "a"})]
    assert measure.latest_inputs(tied) == [{"topic": "a"}, {"topic": "b"}]


@pytest.mark.parametrize(
    ("characters", "warned", "status"),
    [
        (LENGTH_LIMITS["medium"] + 1, False, "over"),
        (LENGTH_LIMITS["medium"], False, "in_range"),
        (LENGTH_TARGET_MINIMUMS["medium"], False, "in_range"),
        (LENGTH_TARGET_MINIMUMS["medium"] - 1, True, "short_warned"),
        (LENGTH_TARGET_MINIMUMS["medium"] - 1, False, "short"),
    ],
)
def test_length_status_compares_the_draft_with_its_target(characters, warned, status):
    assert (
        measure.length_status(
            characters, LENGTH_TARGET_MINIMUMS["medium"], LENGTH_LIMITS["medium"], warned
        )
        == status
    )


def test_a_row_counts_received_and_cited_chunks_and_documents():
    measured = row()
    assert (measured["received_chunks"], measured["received_documents"]) == (3, 2)
    # An ID the writer did not receive is not a citation.
    assert (measured["cited_chunks"], measured["cited_documents"]) == (2, 2)
    assert measured["topic"] == "t" * measure.TOPIC_PREVIEW
    assert (measured["characters"], measured["words"]) == (len("word " * 10), 10)
    assert measured["status"] == "short"
    assert measured["seconds"] == 1.3


def test_a_row_counts_unsupported_and_contradicted_claims_only_when_checked():
    findings = [
        {"code": "unsupported_claim"},
        {"code": "contradicted_claim"},
        {"code": "unlisted_contact_detail"},
    ]
    assert row(review={"status": "checked", "findings": findings})["unsupported"] == 2
    assert row(review={"status": "unchecked", "findings": findings})["unsupported"] is None


def test_a_short_draft_with_a_warning_is_reported_as_warned():
    measured = row(warnings=["The sources were too thin for a medium post."])
    assert measured["status"] == "short_warned"
    assert measured["warnings"] == ["The sources were too thin for a medium post."]


def test_the_summary_gives_the_pass_criteria():
    rows = [
        row(content="x" * LENGTH_TARGET_MINIMUMS["medium"], cited_ids=["c1"]),
        row(warnings=["thin"], cited_ids=["c1", "c2", "c3"]),
        row(review={"status": "checked", "findings": [{"code": "unsupported_claim"}] * 3}),
        row(review={"status": "unchecked", "findings": []}, cost_usd=None),
    ]
    failures = [{"topic": "t", "code": "insufficient_context"}]
    result = measure.summary(rows, failures)
    assert (result["drafts"], result["in_range"]) == (4, 1)
    assert (result["short_warned"], result["short_unwarned"]) == (1, 2)
    assert result["median_cited_chunks"] == 2
    assert result["checked_drafts"] == 3
    assert result["mean_unsupported_per_checked"] == 1
    assert result["failures"] == failures
    # One draft without a known cost makes the total unknown rather than too low.
    assert result["cost_usd"] is None
    empty = measure.summary([], [])
    assert empty["drafts"] == 0 and empty["median_cited_chunks"] is None


def test_a_failure_records_tokens_and_how_far_a_draft_went_over():
    found = measure.failure(
        "t", "generation_output_limit", {"usage": {"completion_tokens": 9}}, "a b"
    )
    assert found == {
        "topic": "t",
        "code": "generation_output_limit",
        "usage": {"completion_tokens": 9},
        "characters": 3,
        "words": 2,
    }
    assert measure.failure("t", "generation_timeout", {}) == {
        "topic": "t",
        "code": "generation_timeout",
    }


def test_topics_can_be_narrowed_by_their_opening_text():
    topics = [{"topic": "short one"}, {"topic": "medium one"}, {"topic": "shorter"}]
    assert measure.chosen(topics, None) == topics
    assert measure.chosen(topics, ["short"]) == [{"topic": "short one"}, {"topic": "shorter"}]
    assert measure.chosen(topics, ["medium", "none"]) == [{"topic": "medium one"}]


def test_a_baseline_without_length_targets_sends_none():
    data = json.loads(measure.writer_message({}, {}, [], LENGTH_LIMITS["short"], None))
    assert set(data) == {"brand", "preferences", "sources", "platform_character_limit"}


def test_the_script_refuses_to_run_without_a_spending_cap(capsys):
    with pytest.raises(SystemExit) as stopped:
        measure.main([])
    assert stopped.value.code == 2
    assert "--max-usd" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        measure.main(["--max-usd", "0"])


# Live path with fake providers


@pytest.fixture
def owner_db(service_api, settings):  # noqa: F811  (fixtures used by name)
    client, factory, _, generation = service_api
    with (
        patch("app.db.SessionLocal", factory),
        patch("scripts.measure_draft_quality.read_only") as read_only,
        patch("app.embeddings.embed_texts", return_value=[[1.0, 0.0, 0.0]]),
    ):
        yield client, factory, generation, read_only


def test_without_a_key_the_run_stops_before_any_call(owner_db):
    _, _, _, read_only = owner_db
    with patch("app.generation_provider.generation_key", return_value=""):
        report = measure.measure(0.5, None)
    assert report["stopped"] == "no generation key is configured"
    assert report["rows"] == []
    read_only.assert_called_once()


def test_without_drafts_the_run_stops_with_a_clear_reason(owner_db):
    _, factory, _, _ = owner_db
    setup_brand(factory)
    assert measure.measure(0.5, None)["stopped"] == "no Ready drafts to take topics from"


def test_each_topic_gets_a_fresh_draft_with_the_writer_message_generation_sends(owner_db):
    client, factory, generation, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    assert client.post("/generation", json=payload(length="short")).status_code == 200
    sent = generation.call_args.args
    with patch("app.generation_provider.chat_completion", side_effect=fake_completion) as call:
        report = measure.measure(0.5, None)
    assert report["stopped"] is None
    system, user, _ = call.call_args.args
    # The script measures exactly what generation sends.
    assert (system, json.loads(user)) == (sent[0], json.loads(sent[1]))
    # Short drafts get v8's prompt and no length target, as generation sends them.
    assert "length_target" not in json.loads(user)
    assert length_target("short") is None
    assert call.call_args.kwargs["budget_usd"] == 0.5
    [measured] = report["rows"]
    assert measured["review"] == "checked" and measured["unsupported"] == 0
    assert measured["cited_chunks"] == measured["received_chunks"] == 1
    assert report["summary"]["drafts"] == 1
    assert report["spent_usd"] > 0


def test_reaching_the_cap_stops_and_keeps_what_was_measured(owner_db):
    client, factory, _, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    for topic in ("first topic", "second topic"):
        assert client.post("/generation", json=payload(topic=topic)).status_code == 200
    calls = iter([fake_completion, GenerationError("generation_spending_limit")])

    def writer(*args, **kwargs):
        step = next(calls)
        if isinstance(step, Exception):
            raise step
        return step(*args, **kwargs)

    with patch("app.generation_provider.chat_completion", side_effect=writer):
        report = measure.measure(0.5, None)
    assert report["stopped"] == "the next writer call could pass --max-usd"
    assert len(report["rows"]) == 1
    assert report["summary"]["drafts"] == 1


def test_a_source_check_that_did_not_finish_is_recorded_and_the_run_goes_on(owner_db):
    client, factory, _, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    for topic in ("first topic", "second topic"):
        assert client.post("/generation", json=payload(topic=topic)).status_code == 200
    with (
        patch("app.generation_provider.chat_completion", side_effect=fake_completion),
        patch(
            "app.grounding.chat_completion",
            side_effect=GenerationError("grounding_review_invalid"),
        ),
    ):
        report = measure.measure(0.5, None)
    assert report["stopped"] is None
    # Both drafts' lengths count; neither adds to the unsupported-claim mean.
    assert [r["review"] for r in report["rows"]] == ["unchecked", "unchecked"]
    assert [r["unsupported"] for r in report["rows"]] == [None, None]
    assert [f["code"] for f in report["summary"]["failures"]] == [
        "review_grounding_review_invalid"
    ] * 2
    assert report["summary"]["checked_drafts"] == 0


def test_writer_only_skips_the_source_check_and_a_draft_over_its_limit_is_measured(owner_db):
    client, factory, _, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    for topic, length in (("long draft", "short"), ("fine draft", "medium")):
        assert (
            client.post("/generation", json=payload(topic=topic, length=length)).status_code == 200
        )

    def writer(system, user, tokens, **kwargs):
        raw, metadata = fake_completion(system, user, tokens, **kwargs)
        if json.loads(user)["preferences"]["length"] == "short":
            data = json.loads(raw) | {"content": "word " * 150}
            raw = json.dumps(data)
        return raw, metadata

    with (
        patch("app.generation_provider.chat_completion", side_effect=writer),
        patch("app.grounding.chat_completion") as check,
    ):
        report = measure.measure(0.5, None, ["long", "fine"], writer_only=True)
    check.assert_not_called()
    [over] = report["summary"]["failures"]
    assert (over["code"], over["words"]) == ("generation_output_limit", 150)
    assert over["characters"] > LENGTH_LIMITS["short"]
    assert over["usage"]["completion_tokens"] == 20
    [measured] = report["rows"]
    assert (measured["review"], measured["unsupported"]) == ("not_requested", None)


def test_a_refused_embedding_stops_the_run_with_its_reason(owner_db):
    client, factory, _, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    assert client.post("/generation", json=payload()).status_code == 200
    with patch(
        "app.embeddings.embed_texts",
        side_effect=EmbeddingError("embedding_authentication_failed"),
    ):
        report = measure.measure(0.5, None)
    assert report["stopped"] == "the topic could not be embedded (embedding_authentication_failed)"
    assert report["rows"] == []


def test_a_source_check_refused_by_the_cap_stops_the_run(owner_db):
    client, factory, _, _ = owner_db
    setup_brand(factory)
    setup_source(factory)
    assert client.post("/generation", json=payload()).status_code == 200
    with (
        patch("app.generation_provider.chat_completion", side_effect=fake_completion),
        patch(
            "app.grounding.chat_completion",
            side_effect=GenerationError("generation_spending_limit"),
        ),
    ):
        report = measure.measure(0.5, None)
    assert report["stopped"] == "the next source check could pass --max-usd"
    assert report["rows"] == []


def test_read_only_connections_refuse_writes():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for database tests")
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    measure.read_only(engine)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            with pytest.raises(InternalError, match="read-only transaction"):
                connection.execute(text("CREATE TEMP TABLE measure_probe (id int)"))
    finally:
        engine.dispose()
