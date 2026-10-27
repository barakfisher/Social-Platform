import json
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.generation_provider import GenerationError
from app.grounding import REVIEW_VERSION, Claim, claims_cover, review_draft


@pytest.mark.parametrize(
    "language,first,intervening,last,draft",
    [
        (
            "en",
            "We grow rosemary.",
            "\nThe tool shed is blue.\n",
            "We grow sage.",
            "We grow rosemary and sage.",
        ),
        (
            "he",
            "אנחנו מגדלים רוזמרין.",
            "\nמחסן הכלים כחול.\n",
            "אנחנו מגדלים מרווה.",
            "אנחנו מגדלים רוזמרין ומרווה.",
        ),
    ],
)
@pytest.mark.parametrize("quote_mode", ["separate", "stitched", "ellipsis", "whitespace"])
def test_nonadjacent_facts_require_separate_exact_excerpts(
    language: str, first: str, intervening: str, last: str, draft: str, quote_mode: str
) -> None:
    source = first + intervening + last
    quotes = {
        "separate": [first, last],
        "stitched": [first + " " + last],
        "ellipsis": [first + " ... " + last],
        "whitespace": [source.replace("\n", " ")],
    }[quote_mode]
    verdict = {
        "accepted": True,
        "issues": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": draft,
                        "supported": True,
                        "evidence": [{"chunk_id": "S1", "quote": quote} for quote in quotes],
                    }
                ],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        if quote_mode == "separate":
            result = review_draft(
                draft, [{"chunk_id": "source", "content": source}], {}, {"language": language}
            )
            assert result["version"] == REVIEW_VERSION == "source-review-v4"
            # Stored provenance maps the reviewer's alias back to the real chunk ID.
            evidence = result["sentences"][0]["claims"][0]["evidence"]
            assert evidence == [{"chunk_id": "source", "quote": quote} for quote in quotes]
        else:
            with pytest.raises(GenerationError, match="^grounding_review_failed$"):
                review_draft(
                    draft,
                    [{"chunk_id": "source", "content": source}],
                    {},
                    {"language": language},
                )


@pytest.mark.parametrize(
    "evidence,error",
    [
        ([{"chunk_id": "S1", "quote": "We grow rosemary. Admission is free."}], "failed"),
        ([{"chunk_id": "other", "quote": "We grow rosemary."}], "failed"),
        ([{"chunk_id": "S1", "quote": None}], "invalid"),
        ([{"chunk_id": None, "quote": "We grow rosemary."}], "invalid"),
        ([{"chunk_id": "S1", "quote": ""}], "invalid"),
        ([{"chunk_id": "S1"}], "invalid"),
        ([], "failed"),
        (None, "invalid"),
    ],
)
def test_evidence_boundaries_fail_closed(evidence: object, error: str) -> None:
    verdict = {
        "accepted": True,
        "issues": [],
        "sentences": [
            {
                "index": 0,
                "claims": [{"text": "We grow rosemary.", "supported": True, "evidence": evidence}],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        with pytest.raises(GenerationError, match=f"^grounding_review_{error}$"):
            review_draft(
                "We grow rosemary.",
                [{"chunk_id": "source", "content": "We grow rosemary."}],
                {},
                {"language": "en"},
            )


ORIGIN_SOURCES = {
    "en": "John Montagu, the fourth Earl of Sandwich, often ate meat between slices of bread.",
    "he": "ג'ון מונטגיו, הרוזן הרביעי מסנדוויץ', נהג לאכול בשר בין פרוסות לחם.",
}
# A clause true in the world but absent from the source, ahead of a sourced remainder.
ORIGIN_CLAUSES = {
    "en": ("The word sandwich is named after ", "John Montagu, the fourth Earl of Sandwich"),
    "he": ("המילה סנדוויץ' נקראת על שמו של ", "ג'ון מונטגיו, הרוזן הרביעי מסנדוויץ'"),
}


def review(language: str, draft: str, claims: list[dict]) -> dict:
    verdict = {"accepted": True, "issues": [], "sentences": [{"index": 0, "claims": claims}]}
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        return review_draft(
            draft,
            [{"chunk_id": "source", "content": ORIGIN_SOURCES[language]}],
            {},
            {"language": language},
        )


def sourced(text: str, quote: str) -> dict:
    return {"text": text, "supported": True, "evidence": [{"chunk_id": "S1", "quote": quote}]}


@pytest.mark.parametrize("language", ["en", "he"])
@pytest.mark.parametrize("mode", ["unclaimed", "unsupported", "unsupported_without_evidence"])
def test_unsourced_clause_fails_even_when_rest_of_sentence_is_quoted(
    language: str, mode: str
) -> None:
    unsourced, sourced_text = ORIGIN_CLAUSES[language]
    draft = unsourced + sourced_text + "."
    quote = sourced_text
    claims = {
        # Regression for the v3 miss: exact quotes cover only part of the sentence.
        "unclaimed": [sourced(sourced_text, quote)],
        "unsupported": [
            {
                "text": unsourced.strip(),
                "supported": False,
                "evidence": [{"chunk_id": "S1", "quote": quote}],
            },
            sourced(sourced_text, quote),
        ],
        "unsupported_without_evidence": [
            {"text": unsourced.strip(), "supported": False, "evidence": []},
            sourced(sourced_text, quote),
        ],
    }[mode]
    with pytest.raises(GenerationError, match="^grounding_review_failed$"):
        review(language, draft, claims)


@pytest.mark.parametrize("language", ["en", "he"])
def test_fully_claimed_sourced_sentence_passes(language: str) -> None:
    _, sourced_text = ORIGIN_CLAUSES[language]
    result = review(language, sourced_text + ".", [sourced(sourced_text, sourced_text)])
    assert result["status"] == "passed"
    assert result["version"] == REVIEW_VERSION


def claims(*texts: str) -> list[Claim]:
    return [Claim(text=text, supported=True, evidence=[]) for text in texts]


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("We grow rosemary and sage.", ["We grow rosemary", "sage"]),
        ("We grow rosemary, sage.", ["We grow rosemary", "sage"]),
        ("אנחנו מגדלים רוזמרין ומרווה.", ["אנחנו מגדלים רוזמרין", "מרווה"]),
        ("אנחנו מגדלים רוזמרין וגם מרווה.", ["אנחנו מגדלים רוזמרין", "מרווה"]),
    ],
)
def test_connectives_and_punctuation_may_stay_outside_claims(sentence: str, texts: list[str]):
    assert claims_cover(sentence, claims(*texts))


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("Today we grow rosemary.", ["we grow rosemary"]),
        ("כיום אנחנו מגדלים רוזמרין.", ["אנחנו מגדלים רוזמרין"]),
        ("We grow rosemary since 1762.", ["We grow rosemary since"]),
        ("We grow rosemary and sage.", ["sage", "We grow rosemary"]),
        ("We grow rosemary.", ["We grow rosemary", "rosemary"]),
        ("We grow rosemary.", ["We grow fresh rosemary"]),
        ("We grow rosemary.", []),
    ],
    ids=[
        "en-qualifier",
        "he-qualifier",
        "number",
        "out-of-order",
        "overlap",
        "not-in-sentence",
        "empty",
    ],
)
def test_content_words_outside_claims_fail_coverage(sentence: str, texts: list[str]):
    assert not claims_cover(sentence, claims(*texts))


def test_claim_count_is_bounded() -> None:
    draft = " ".join(["rosemary"] * 21) + "."
    with pytest.raises(GenerationError, match="^grounding_review_invalid$"):
        review("en", draft, [sourced("rosemary", "John Montagu")] * 21)


def test_reviewer_sees_aliases_and_unknown_aliases_fail() -> None:
    sources = [
        {"chunk_id": "0b7d1c9e-0000-4000-8000-000000000001", "content": "We grow rosemary."},
        {"chunk_id": "0b7d1c9e-0000-4000-8000-000000000002", "content": "We grow sage."},
    ]
    verdict = {
        "accepted": True,
        "issues": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": "We grow rosemary",
                        "supported": True,
                        "evidence": [{"chunk_id": "S1", "quote": "We grow rosemary."}],
                    },
                    {
                        "text": "sage",
                        "supported": True,
                        "evidence": [{"chunk_id": "S2", "quote": "We grow sage."}],
                    },
                ],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})) as complete:
        result = review_draft("We grow rosemary and sage.", sources, {}, {"language": "en"})
    sent = json.loads(complete.call_args.args[1])["sources"]
    assert [s["chunk_id"] for s in sent] == ["S1", "S2"]
    assert all(source["chunk_id"] not in complete.call_args.args[1] for source in sources)
    cited = [e["chunk_id"] for c in result["sentences"][0]["claims"] for e in c["evidence"]]
    assert cited == [sources[0]["chunk_id"], sources[1]["chunk_id"]]
    # A real chunk ID is not an alias the reviewer was given, so citing it fails closed.
    verdict["sentences"][0]["claims"][1]["evidence"][0]["chunk_id"] = sources[1]["chunk_id"]
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        with pytest.raises(GenerationError, match="^grounding_review_failed$"):
            review_draft("We grow rosemary and sage.", sources, {}, {"language": "en"})


def test_reviewer_requests_its_own_output_limit() -> None:
    verdict = {
        "accepted": True,
        "issues": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": "We grow rosemary.",
                        "supported": True,
                        "evidence": [{"chunk_id": "S1", "quote": "We grow rosemary."}],
                    }
                ],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})) as complete:
        review_draft(
            "We grow rosemary.",
            [{"chunk_id": "source", "content": "We grow rosemary."}],
            {},
            {"language": "en"},
        )
    limit = get_settings().generation_review_max_output_tokens
    assert complete.call_args.kwargs["output_tokens"] == limit
