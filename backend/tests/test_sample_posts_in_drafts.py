# ruff: noqa: F811  (pytest fixtures imported by name)
"""The writer takes facts and style from sample posts, never their message
(docs/implementation.md, "sample posts in drafts")."""

import json

import pytest

from app.generation import SAMPLE_POSTS_RULE, WRITER_SYSTEMS
from app.restatement import restated_sentences, topic_words
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    payload,
    service_api,
    settings,
    setup_brand,
    setup_source,
)

# The owner's first sample post and the draft that restated it (run 27895904, 2026-11-01).
SAMPLE_POST = (
    "לא כל מי שהצליח בחיים יודע לעזור לאחרים להצליח.\n"
    "ניסיון חיים הוא נכס. מנטורינג הוא מקצוע.\n"
    "אנחנו לא מלמדים רק איך ללוות אחרים.\n"
)
RESTATING_DRAFT = (
    "אחרי יותר מעשרים שנה של ליווי מנהלים בצמתי חיים, גיליתי תובנה שהפתיעה גם אותי: "
    "לא כל מי שהצליח יודע לעזור לאחרים להצליח. ניסיון חיים הוא נכס, אבל מנטורינג הוא "
    "מקצוע בפני עצמו.\n\nמה הניסיון שלכם לימד אתכם על שינוי אצל אנשים?"
)
NEW_DRAFT = "מנטור טוב יודע מתי לשתוק. השקט נותן לאדם מקום לשמוע את עצמו."


def lines(text: str) -> set[frozenset[str]]:
    return {topic_words(line) for line in text.splitlines()} - {frozenset()}


def writer_returns(generation, content: str, warnings: list[str] | None = None):
    def complete(system, user, tokens, **kwargs):
        data = json.loads(user)
        return json.dumps(
            {
                "content": content,
                "source_ids": [data["sources"][0]["chunk_id"]],
                "warnings": warnings or [],
            }
        ), {"model": "test/model", "usage": {"cost_usd": 0.0001}}

    generation.side_effect = complete


# Writer prompts


@pytest.mark.parametrize("level", sorted(WRITER_SYSTEMS))
def test_every_writer_prompt_ends_with_the_sample_post_rule(level):
    assert WRITER_SYSTEMS[level].endswith(SAMPLE_POSTS_RULE)


def test_the_rule_allows_facts_and_style_and_forbids_the_message():
    rule = " ".join(SAMPLE_POSTS_RULE.split())
    assert '"sample_posts"' in rule and '"knowledge"' in rule
    assert "facts about the brand" in rule
    assert "voice, structure and rhythm" in rule
    assert "Never reuse a sample post's message, angle, opening" in rule


# Sources


def test_the_writer_sees_each_sources_kind(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory, content="Rosemary grows.", title="Garden")
    setup_source(factory, content="Our garden post.", title="Posts", kind="sample_posts")
    response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    sent = json.loads(generation.call_args.args[1])["sources"]
    assert {(s["title"], s["kind"]) for s in sent} == {
        ("Garden", "knowledge"),
        ("Posts", "sample_posts"),
    }


# Restatement


def test_a_draft_sentence_that_restates_a_sample_post_is_found():
    restated = restated_sentences(RESTATING_DRAFT, lines(SAMPLE_POST))
    assert restated == ["לא כל מי שהצליח יודע לעזור לאחרים להצליח"]


def test_a_new_draft_and_a_short_shared_phrase_are_not_restatements():
    assert restated_sentences(NEW_DRAFT, lines(SAMPLE_POST)) == []
    # A phrase too short to be a post's idea ("not necessarily") is shared, not restated.
    assert restated_sentences("לא בהכרח. " + NEW_DRAFT, lines("לא בהכרח.")) == []


def test_restating_a_sample_post_adds_a_warning_and_keeps_the_writers(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory, content=SAMPLE_POST, title="Posts", kind="sample_posts")
    writer_returns(generation, RESTATING_DRAFT, ["Writer note"])
    response = client.post("/generation", json=payload(language="he"))
    assert response.status_code == 200, response.text
    warnings = response.json()["warnings"]
    assert warnings[0] == "Writer note"
    assert len(warnings) == 2
    assert "לא כל מי שהצליח יודע לעזור לאחרים להצליח" in warnings[1]


def test_restating_a_knowledge_document_is_not_flagged(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory, content=SAMPLE_POST, title="Notes")
    writer_returns(generation, RESTATING_DRAFT)
    response = client.post("/generation", json=payload(language="he"))
    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == []
