# ruff: noqa: F811  (pytest fixtures imported by name)
"""The knowledge level: Knowledge Base only, or with general professional knowledge
(docs/implementation.md, "general professional knowledge in drafts")."""

import hashlib
import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.generation import (
    CHARS_PER_WORD,
    DEFAULT_KNOWLEDGE_LEVEL,
    GENERAL_SYSTEM,
    KNOWLEDGE_BASE_SYSTEM,
    LENGTH_LIMITS,
    LENGTH_TARGET_MINIMUMS,
    LENGTH_TARGET_WORDS,
    PROMPT_VERSION,
    SAMPLE_POSTS_RULE,
    SHORT_WRITER_SYSTEMS,
    STORED_KNOWLEDGE_LEVEL,
    WRITER_SYSTEMS,
    length_target,
    writer_system,
)
from app.grounding import REVIEW_SYSTEM, Review, check_draft, prompt_tokens
from app.models import GenerationRun, Post
from tests.test_generation import (  # noqa: F401  (fixtures used by name)
    payload,
    service_api,
    settings,
    setup_brand,
    setup_source,
)

SOURCE = "Rosemary grows in the community garden."
GENERAL = "A mentor shortens the learning curve."
# SHA-256 of grounded-post-v6's writer prompt without its two length lines ("Length is a
# maximum ... Never pad a short source." and "Prefer a shorter faithful post ..."): every
# other rule of "Knowledge Base only" stays word for word (SP-28).
V6_RULES_SHA256 = "165d0c32206e792d41a183d10783e5fb0d4a50bb1650931f7b73cd9a7ef1781d"
LENGTH_RULE_START = "\nLength is a target range"


def flat(text: str) -> str:
    return " ".join(text.split())


def claim(text, kind="factual", supported=False, contradicted=False, evidence=None):
    return {
        "text": text,
        "kind": kind,
        "supported": supported,
        "contradicted": contradicted,
        "evidence": evidence or [],
    }


def sourced(text=SOURCE):
    return claim(text, supported=True, evidence=[{"chunk_id": "S1", "quote": SOURCE}])


def checked(sentences, level, brand=None, content=None):
    """Review one claim per sentence at a knowledge level, with the reviewer stubbed."""
    raw = json.dumps(
        {
            "issues": [],
            "blocking": [],
            "sentences": [{"index": i, "claims": [c]} for i, c in enumerate(sentences)],
        }
    )
    content = content or " ".join(c["text"] for c in sentences)
    preferences = (
        {"language": "en"} if level is None else {"language": "en", "knowledge_level": level}
    )
    with patch("app.grounding.chat_completion", return_value=(raw, {})):
        return check_draft(
            content, [{"chunk_id": "c1", "content": SOURCE}], brand or {}, preferences
        )


def stored_claims(review):
    return [c for sentence in review["sentences"] for c in sentence["claims"]]


# Writer prompts


def test_knowledge_base_prompt_keeps_every_v6_rule_and_only_its_length_lines_change():
    rules = KNOWLEDGE_BASE_SYSTEM.removesuffix(SAMPLE_POSTS_RULE)
    assert rules != KNOWLEDGE_BASE_SYSTEM
    rules = rules[: rules.index(LENGTH_RULE_START)]
    assert hashlib.sha256(rules.encode()).hexdigest() == V6_RULES_SHA256
    assert WRITER_SYSTEMS == {"knowledge_base": KNOWLEDGE_BASE_SYSTEM, "general": GENERAL_SYSTEM}


@pytest.mark.parametrize("system", [KNOWLEDGE_BASE_SYSTEM, GENERAL_SYSTEM])
def test_both_levels_aim_for_the_length_range_and_warn_when_sources_are_thin(system):
    prompt = flat(system)
    for length, limit in LENGTH_LIMITS.items():
        assert f"{length} {LENGTH_TARGET_MINIMUMS[length]}–{limit}" in prompt
    for rule in ("Never pad", "Prefer a shorter"):
        assert rule not in prompt
    assert "For medium and long posts, length_target in the data" in prompt
    assert "plan enough points for it before writing" in prompt
    assert "The character maximum is a hard limit" in prompt
    assert "sources were too thin for the chosen length" in prompt
    # Reasoning writers spent their whole output limit counting characters.
    assert "Check the length" not in prompt


# SHA-256 of grounded-post-v8's writer prompts as merged on main: short drafts use them
# unchanged (SP-28).
V8_SYSTEM_SHA256 = {
    "knowledge_base": "784f9c1ae5916457689537bb029c07b1e526528081e9cf05f86bd4c367967447",
    "general": "c890811c1bdc633383945e077ea1a35ab56f05c139160a8c76076781862a747a",
}


@pytest.mark.parametrize("level", sorted(WRITER_SYSTEMS))
def test_short_drafts_keep_grounded_post_v8_word_for_word(level):
    assert sorted(SHORT_WRITER_SYSTEMS) == sorted(WRITER_SYSTEMS)
    system = SHORT_WRITER_SYSTEMS[level]
    assert hashlib.sha256(system.encode()).hexdigest() == V8_SYSTEM_SHA256[level]
    assert writer_system(level, "short") == system
    for length in ("medium", "long"):
        assert writer_system(level, length) == WRITER_SYSTEMS[level]
    assert length_target("short") is None


def test_general_prompt_allows_general_knowledge_and_the_knowledge_base_level_does_not():
    general, knowledge_base = flat(GENERAL_SYSTEM), flat(KNOWLEDGE_BASE_SYSTEM)
    assert "Never add outside/world knowledge" in knowledge_base
    assert "Never add outside/world knowledge" not in general
    assert "general knowledge that explains it" in general
    assert "general knowledge" not in knowledge_base.split(LENGTH_RULE_START.strip())[1]
    assert "main message and angle come from the sources" in general
    assert "first-person story or experience. Never invent these." in general


@pytest.mark.parametrize("length", sorted(LENGTH_TARGET_WORDS))
def test_the_word_target_lands_inside_the_character_range(length):
    # At the fewest measured characters per word the minimum is reached; at the most, the
    # maximum is not passed.
    fewest, most = LENGTH_TARGET_WORDS[length]
    low, high = CHARS_PER_WORD
    assert LENGTH_TARGET_MINIMUMS[length] < LENGTH_LIMITS[length]
    assert fewest < most
    assert fewest * low >= LENGTH_TARGET_MINIMUMS[length]
    assert most * high <= LENGTH_LIMITS[length]


# Writer requests


@pytest.mark.parametrize("level", sorted(WRITER_SYSTEMS))
def test_each_level_sends_its_own_writer_prompt(service_api, level):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    response = client.post("/generation", json=payload(knowledge_level=level))
    assert response.status_code == 200, response.text
    system, user, _ = generation.call_args.args
    assert system == WRITER_SYSTEMS[level]
    assert json.loads(user)["preferences"]["knowledge_level"] == level
    assert response.json()["metadata"]["preferences"]["knowledge_level"] == level
    with factory() as session:
        run = session.query(GenerationRun).one()
        assert run.inputs["knowledge_level"] == level


@pytest.mark.parametrize("length", sorted(LENGTH_LIMITS))
def test_the_writer_gets_the_chosen_lengths_target(service_api, length):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    response = client.post("/generation", json=payload(length=length))
    assert response.status_code == 200, response.text
    data = json.loads(generation.call_args.args[1])
    assert data["platform_character_limit"] == LENGTH_LIMITS[length]
    characters = {"min": LENGTH_TARGET_MINIMUMS[length], "max": LENGTH_LIMITS[length]}
    if length == "short":
        # As in v8: every v9 wording pushed short drafts past their maximum.
        assert "length_target" not in data
        assert generation.call_args.args[0] == SHORT_WRITER_SYSTEMS[DEFAULT_KNOWLEDGE_LEVEL]
    else:
        assert data["length_target"] == {
            "characters": characters,
            "words": dict(zip(("min", "max"), LENGTH_TARGET_WORDS[length], strict=True)),
        }


def test_an_omitted_level_is_general_knowledge(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    response = client.post("/generation", json=payload())
    assert response.status_code == 200, response.text
    assert DEFAULT_KNOWLEDGE_LEVEL == "general"
    assert generation.call_args.args[0] == WRITER_SYSTEMS[DEFAULT_KNOWLEDGE_LEVEL]


def test_an_unknown_level_is_rejected_before_any_call(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    response = client.post("/generation", json=payload(knowledge_level="web"))
    assert response.status_code == 422
    generation.assert_not_called()


def test_repeating_a_request_at_another_level_is_a_conflict(service_api):
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    first = payload(knowledge_level="general")
    assert client.post("/generation", json=first).status_code == 200
    other = client.post("/generation", json={**first, "knowledge_level": "knowledge_base"})
    assert other.status_code == 409
    assert other.json()["error"]["message"] == "generation_request_conflict"
    assert generation.call_count == 1


def test_the_writer_prompt_guard_counts_the_longer_prompt(service_api, settings):  # noqa: F811
    client, factory, _, generation = service_api
    setup_brand(factory)
    setup_source(factory)
    assert prompt_tokens(GENERAL_SYSTEM) > prompt_tokens(KNOWLEDGE_BASE_SYSTEM)
    kb = client.post("/generation", json=payload(knowledge_level="knowledge_base"))
    assert kb.status_code == 200, kb.text
    # Room for the Knowledge Base prompt with its data, not for the general one.
    settings.generation_prompt_budget = kb.json()["metadata"]["prompt_tokens_estimate"]
    again = client.post("/generation", json=payload(knowledge_level="knowledge_base"))
    assert again.status_code == 200, again.text
    general = client.post("/generation", json=payload(knowledge_level="general"))
    assert general.status_code == 409
    assert general.json()["error"]["message"] == "generation_prompt_limit"


@pytest.mark.parametrize("level", sorted(WRITER_SYSTEMS))
def test_a_check_judges_general_claims_at_the_draft_level(service_api, level):
    client, factory, _, _ = service_api
    setup_brand(factory)
    setup_source(factory)
    generated = client.post("/generation", json=payload(knowledge_level=level)).json()

    def general_review(system, user, tokens, **kwargs):
        data = json.loads(user)
        assert data["preferences"]["knowledge_level"] == level
        return json.dumps(
            {
                "issues": [],
                "blocking": [],
                "sentences": [
                    {"index": s["index"], "claims": [claim(s["text"], kind="general")]}
                    for s in data["sentences"]
                ],
            }
        ), {}

    with patch("app.grounding.chat_completion", side_effect=general_review):
        response = client.post(f"/generation/{generated['id']}/review", json={})
    assert response.status_code == 200, response.text
    findings = [f["code"] for f in response.json()["metadata"]["grounding_review"]["findings"]]
    assert ("unsupported_claim" in findings) == (level == "knowledge_base")


def test_drafts_stored_before_levels_are_checked_as_knowledge_base_only(service_api):
    client, factory, _, _ = service_api
    setup_brand(factory)
    setup_source(factory)
    generated = client.post("/generation", json=payload()).json()
    with factory.begin() as session:
        run = session.get(GenerationRun, generated["id"])
        run.inputs = {k: v for k, v in run.inputs.items() if k != "knowledge_level"}
    sent = []

    def record(system, user, tokens, **kwargs):
        data = json.loads(user)
        sent.append(data["preferences"]["knowledge_level"])
        return json.dumps(
            {
                "issues": [],
                "blocking": [],
                "sentences": [
                    {"index": s["index"], "claims": [claim(s["text"], kind="general")]}
                    for s in data["sentences"]
                ],
            }
        ), {}

    with patch("app.grounding.chat_completion", side_effect=record):
        response = client.post(f"/generation/{generated['id']}/review", json={})
    assert response.status_code == 200, response.text
    assert sent == [STORED_KNOWLEDGE_LEVEL] == ["knowledge_base"]
    review = response.json()["metadata"]["grounding_review"]
    assert review["findings"][0]["code"] == "unsupported_claim"


def test_saved_drafts_from_before_levels_are_checked_as_knowledge_base_only(service_api):
    client, factory, _, _ = service_api
    setup_brand(factory)
    setup_source(factory)
    generated = client.post("/generation", json=payload()).json()
    saved = client.post(
        "/posts",
        json={
            "platform": "linkedin",
            "language": "en",
            "content": generated["content"],
            "save_key": str(uuid4()),
            "generation_run_id": generated["id"],
        },
    ).json()
    with factory.begin() as session:
        post = session.get(Post, saved["id"])
        settings = dict(post.generation_settings)
        settings["preferences"] = {
            k: v for k, v in settings["preferences"].items() if k != "knowledge_level"
        }
        post.generation_settings = settings
    sent = []

    def record(system, user, tokens, **kwargs):
        data = json.loads(user)
        sent.append(data["preferences"]["knowledge_level"])
        return json.dumps(
            {
                "issues": [],
                "blocking": [],
                "sentences": [
                    {"index": s["index"], "claims": [claim(s["text"], kind="general")]}
                    for s in data["sentences"]
                ],
            }
        ), {}

    with patch("app.grounding.chat_completion", side_effect=record):
        response = client.post(f"/posts/{saved['id']}/review", json={"version": 1})
    assert response.status_code == 200, response.text
    assert sent == [STORED_KNOWLEDGE_LEVEL]
    review = response.json()["generation_settings"]["grounding_review"]
    assert review["findings"][0]["code"] == "unsupported_claim"


def test_the_writer_prompt_version_names_this_change():
    assert PROMPT_VERSION == "grounded-post-v9"


def test_the_general_prompt_keeps_out_persuasive_product_descriptions():
    assert "Do not add persuasive product descriptions." in flat(GENERAL_SYSTEM)


# Source check


def test_the_reviewer_is_told_about_general_claims():
    assert "- general: a widely accepted statement of professional knowledge" in REVIEW_SYSTEM
    kinds = Review.model_json_schema()["$defs"]["Claim"]["properties"]["kind"]["enum"]
    assert kinds == ["factual", "general", "creative"]


def test_a_general_claim_is_no_finding_at_the_general_level():
    review = checked([sourced(), claim(GENERAL, kind="general")], "general")
    assert review["status"] == "checked" and review["findings"] == []
    assert [c["kind"] for c in stored_claims(review)] == ["factual", "general"]


@pytest.mark.parametrize("level", ["knowledge_base", None])
def test_a_general_claim_is_unsupported_without_the_general_level(level):
    review = checked([sourced(), claim(GENERAL, kind="general", supported=True)], level)
    assert review["findings"] == [
        {"code": "unsupported_claim", "sentence": GENERAL, "claim": GENERAL.rstrip(".")}
    ]
    stored = stored_claims(review)[1]
    assert stored["kind"] == "factual" and stored["supported"] is False


@pytest.mark.parametrize(
    "text",
    [
        "Mentoring makes people 3 times faster.",
        "Mentoring lifts retention by half %.",
        "Mentoring costs less than ₪ courses.",
        "Cedar Garden mentors shorten the learning curve.",
        "Mentors at cedar garden shorten the learning curve.",
    ],
)
def test_a_general_claim_with_specifics_is_unsupported(text):
    review = checked([claim(text, kind="general")], "general", brand={"name": "Cedar Garden"})
    assert [f["code"] for f in review["findings"]] == ["unsupported_claim"]
    assert stored_claims(review)[0]["kind"] == "factual"


@pytest.mark.parametrize("level", sorted(WRITER_SYSTEMS))
def test_a_contradicted_general_claim_is_reported_as_contradicted(level):
    review = checked([claim(GENERAL, kind="general", contradicted=True)], level)
    assert [f["code"] for f in review["findings"]] == ["contradicted_claim"]
    assert stored_claims(review)[0]["kind"] == "factual"
    assert review["knowledge_share"]["general_claims"] == 0


def test_general_claims_keep_no_evidence_and_unverifiable_quotes_do_not_fail_the_check():
    quote = [{"chunk_id": "S1", "quote": "MODEL PROSE, NOT IN THE SOURCE"}]
    review = checked([claim(GENERAL, kind="general", supported=True, evidence=quote)], "general")
    assert review["status"] == "checked"
    assert stored_claims(review)[0]["evidence"] == []


def test_a_general_claim_must_still_cover_its_sentence():
    review = checked([claim("A mentor shortens", kind="general")], "general", content=GENERAL)
    assert review["status"] == "unchecked" and review["reason"] == "grounding_review_invalid"


def test_the_share_counts_sourced_general_and_unsupported_claims():
    review = checked(
        [
            sourced(),
            claim(GENERAL, kind="general"),
            claim("An outside view helps see the whole picture.", kind="general"),
            claim("The garden won a prize."),
            claim("Come and visit!", kind="creative"),
        ],
        "general",
    )
    assert review["knowledge_share"] == {
        "sourced_claims": 1,
        "general_claims": 2,
        "unsupported_claims": 1,
        "percent": round(100 * 1 / 4),
        "general_sentences": 2,
    }


def test_the_share_has_no_percent_without_claims_to_count():
    review = checked([claim("Come and visit!", kind="creative")], "general")
    assert review["knowledge_share"]["percent"] is None
