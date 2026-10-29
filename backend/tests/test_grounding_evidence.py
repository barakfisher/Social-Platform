import json
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.generation_provider import GenerationError
from app.grounding import (
    CONNECTIVES,
    REVIEW_SYSTEM,
    REVIEW_VERSION,
    Claim,
    claim_spans,
    claims_cover,
    matched_quote,
    review_draft,
)


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
        "issues": [],
        "blocking": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": draft,
                        "kind": "factual",
                        "supported": True,
                        "contradicted": False,
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
            assert result["version"] == REVIEW_VERSION == "source-review-v7"
            # Stored provenance maps the reviewer's alias back to the real chunk ID.
            evidence = result["sentences"][0]["claims"][0]["evidence"]
            assert evidence == [{"chunk_id": "source", "quote": quote} for quote in quotes]
        else:
            with pytest.raises(GenerationError, match="^grounding_review_invalid$"):
                review_draft(
                    draft,
                    [{"chunk_id": "source", "content": source}],
                    {},
                    {"language": language},
                )


@pytest.mark.parametrize(
    "evidence,error",
    [
        ([{"chunk_id": "S1", "quote": "We grow rosemary. Admission is free."}], "invalid"),
        ([{"chunk_id": "other", "quote": "We grow rosemary."}], "invalid"),
        ([{"chunk_id": "S1", "quote": None}], "invalid"),
        ([{"chunk_id": None, "quote": "We grow rosemary."}], "invalid"),
        ([{"chunk_id": "S1", "quote": ""}], "invalid"),
        ([{"chunk_id": "S1"}], "invalid"),
        ([], "invalid"),
        (None, "invalid"),
    ],
)
def test_unverifiable_evidence_is_a_technical_failure(evidence: object, error: str) -> None:
    verdict = {
        "issues": [],
        "blocking": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": "We grow rosemary.",
                        "kind": "factual",
                        "supported": True,
                        "contradicted": False,
                        "evidence": evidence,
                    }
                ],
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
    verdict = {"issues": [], "blocking": [], "sentences": [{"index": 0, "claims": claims}]}
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        return review_draft(
            draft,
            [{"chunk_id": "source", "content": ORIGIN_SOURCES[language]}],
            {},
            {"language": language},
        )


def sourced(text: str, quote: str) -> dict:
    return {
        "text": text,
        "kind": "factual",
        "supported": True,
        "contradicted": False,
        "evidence": [{"chunk_id": "S1", "quote": quote}],
    }


@pytest.mark.parametrize("language", ["en", "he"])
@pytest.mark.parametrize("mode", ["unclaimed", "unsupported", "unsupported_without_evidence"])
def test_unsourced_clause_is_found_even_when_rest_of_sentence_is_quoted(
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
                "kind": "factual",
                "supported": False,
                "contradicted": False,
                "evidence": [{"chunk_id": "S1", "quote": quote}],
            },
            sourced(sourced_text, quote),
        ],
        "unsupported_without_evidence": [
            {
                "text": unsourced.strip(),
                "kind": "factual",
                "supported": False,
                "contradicted": False,
                "evidence": [],
            },
            sourced(sourced_text, quote),
        ],
    }[mode]
    if mode == "unclaimed":
        # Coverage the server cannot verify is a failed review, never a clean pass.
        with pytest.raises(GenerationError, match="^grounding_review_invalid$"):
            review(language, draft, claims)
        return
    result = review(language, draft, claims)
    assert result["findings"] == [
        {"code": "unsupported_claim", "sentence": draft, "claim": unsourced.strip()}
    ]


@pytest.mark.parametrize("language", ["en", "he"])
def test_fully_claimed_sourced_sentence_passes(language: str) -> None:
    _, sourced_text = ORIGIN_CLAUSES[language]
    result = review(language, sourced_text + ".", [sourced(sourced_text, sourced_text)])
    assert result["status"] == "checked" and result["findings"] == []
    assert result["version"] == REVIEW_VERSION


def claims(*texts: str) -> list[Claim]:
    return [
        Claim(text=text, kind="factual", supported=True, contradicted=False, evidence=[])
        for text in texts
    ]


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("We grow rosemary and sage.", ["We grow rosemary", "sage"]),
        ("We grow rosemary, sage.", ["We grow rosemary", "sage"]),
        ("אנחנו מגדלים רוזמרין ומרווה.", ["אנחנו מגדלים רוזמרין", "מרווה"]),
        ("אנחנו מגדלים רוזמרין וגם מרווה.", ["אנחנו מגדלים רוזמרין", "מרווה"]),
        # A live GPT-5.6-terra review left the opening discourse word outside the claim.
        (
            "כך, מנטורינג יוצר מכנה משותף שמאפשר צמיחה והתפתחות בכל תחום בו הוא מיושם.",
            ["מנטורינג יוצר מכנה משותף שמאפשר צמיחה והתפתחות בכל תחום בו הוא מיושם"],
        ),
        ("לכן, אנחנו מגדלים רוזמרין.", ["אנחנו מגדלים רוזמרין"]),
        ("Therefore, we grow rosemary.", ["we grow rosemary"]),
        # Relative and listing words a live GPT-5.6-terra review left outside its claims.
        (
            "מנטורינג הוא תהליך בו אדם מנוסה משמש כיועץ.",
            ["מנטורינג הוא תהליך", "אדם מנוסה משמש כיועץ"],
        ),
        (
            "קיימים מודלים שונים, כולל מודל קבוצתי.",
            ["קיימים מודלים שונים", "מודל קבוצתי"],
        ),
        ("זה התחום שבו אנחנו עובדים.", ["זה התחום", "אנחנו עובדים"]),
        ("המנטור אשר ליווה אותנו.", ["המנטור", "ליווה אותנו"]),
    ],
)
def test_connectives_and_punctuation_may_stay_outside_claims(sentence: str, texts: list[str]):
    assert claims_cover(sentence, claims(*texts))


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("Today we grow rosemary.", ["we grow rosemary"]),
        ("כיום אנחנו מגדלים רוזמרין.", ["אנחנו מגדלים רוזמרין"]),
        ("לא אנחנו מגדלים רוזמרין.", ["אנחנו מגדלים רוזמרין"]),
        ("ביוון, שם מנטור היה חונך.", ["ביוון", "מנטור היה חונך"]),
        ("We grow rosemary since 1762.", ["We grow rosemary since"]),
        ("We grow rosemary and sage.", ["sage", "We grow rosemary"]),
        ("We grow rosemary.", ["We grow rosemary", "rosemary"]),
        ("We grow rosemary.", ["We grow fresh rosemary"]),
        ("We grow rosemary.", []),
    ],
    ids=[
        "en-qualifier",
        "he-qualifier",
        "he-negation",
        "he-place",
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
        "issues": [],
        "blocking": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": "We grow rosemary",
                        "kind": "factual",
                        "supported": True,
                        "contradicted": False,
                        "evidence": [{"chunk_id": "S1", "quote": "We grow rosemary."}],
                    },
                    {
                        "text": "sage",
                        "kind": "factual",
                        "supported": True,
                        "contradicted": False,
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
    # A real chunk ID is not an alias the reviewer was given, so the review is unverifiable.
    verdict["sentences"][0]["claims"][1]["evidence"][0]["chunk_id"] = sources[1]["chunk_id"]
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        with pytest.raises(GenerationError, match="^grounding_review_invalid$"):
            review_draft("We grow rosemary and sage.", sources, {}, {"language": "en"})


def test_reviewer_requests_its_own_output_limit() -> None:
    verdict = {
        "issues": [],
        "blocking": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        "text": "We grow rosemary.",
                        "kind": "factual",
                        "supported": True,
                        "contradicted": False,
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


def test_review_cut_off_by_the_output_limit_has_its_own_code() -> None:
    truncated = GenerationError("generation_output_truncated", {"output_tokens": 4000})
    with patch("app.grounding.chat_completion", side_effect=truncated):
        with pytest.raises(GenerationError, match="^grounding_review_truncated$") as raised:
            review_draft(
                "We grow rosemary.",
                [{"chunk_id": "source", "content": "We grow rosemary."}],
                {},
                {"language": "en"},
            )
    assert raised.value.metadata == {"output_tokens": 4000}


def test_reviewer_prompt_lists_exactly_the_words_coverage_accepts() -> None:
    # The model and the coverage check must agree on which words may stay outside claims.
    listed = REVIEW_SYSTEM.split("the words in this list:\n", 1)[1].split("\n", 1)[0]
    assert set(listed.split()) == CONNECTIVES


def test_quote_carrying_one_hebrew_prefix_verifies_and_stores_source_text() -> None:
    # Live GPT-5.6-terra quoted the draft's "שנהג" for the source's "נהג" (2026-10-27).
    claim = "שנהג לאכול בשר בין פרוסות לחם"
    result = review("he", claim + ".", [sourced(claim, claim)])
    assert result["status"] == "checked" and result["findings"] == []
    evidence = result["sentences"][0]["claims"][0]["evidence"]
    assert evidence == [{"chunk_id": "source", "quote": "נהג לאכול בשר בין פרוסות לחם"}]


@pytest.mark.parametrize(
    "quote",
    [
        "ושנהג לאכול בשר",  # two prefix letters
        "תנהג לאכול בשר",  # not a prefix letter
        "ש נהג לאכול בשר",  # prefix detached from the word
    ],
)
def test_prefix_tolerance_is_one_attached_hebrew_prefix_only(quote: str) -> None:
    claim = "נהג לאכול בשר"
    with pytest.raises(GenerationError, match="^grounding_review_invalid$"):
        review("he", claim + ".", [sourced(claim, quote)])


@pytest.mark.parametrize(
    "sentence,texts,spans",
    [
        (
            "The museum opens on Tuesdays.",
            ["The museum", "opens Tuesdays"],
            ["The museum", "opens on Tuesdays"],
        ),
        ("המתנדבים גם מגדלים מרווה.", ["המתנדבים מגדלים מרווה"], ["המתנדבים גם מגדלים מרווה"]),
        # A dropped one-letter prefix (ב, "in") inside the claim.
        (
            "המתנדבים נפגשים בגינה ביום חמישי.",
            ["המתנדבים נפגשים גינה ביום חמישי"],
            ["המתנדבים נפגשים בגינה ביום חמישי"],
        ),
        (
            "Volunteers meet on Thursdays, at noon.",
            ["Volunteers meet on Thursdays at noon"],
            ["Volunteers meet on Thursdays, at noon"],
        ),
        # SP-24: live Terra reviews left the Hebrew copula between two exact claims.
        (
            "היעד המרכזי של התהליך הוא שהמתאמן ירכוש כלים.",
            ["היעד המרכזי של התהליך", "שהמתאמן ירכוש כלים"],
            ["היעד המרכזי של התהליך", "שהמתאמן ירכוש כלים"],
        ),
    ],
    ids=["en-dropped-on", "he-dropped-gam", "he-dropped-prefix", "en-dropped-comma", "he-copula"],
)
def test_claims_may_skip_connectives_and_are_stored_as_draft_text(
    sentence: str, texts: list[str], spans: list[str]
):
    found = claim_spans(sentence, claims(*texts))
    assert found is not None
    assert [sentence[start:end] for start, end in found] == spans


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("Volunteers meet at 6 PM.", ["Volunteers meet at 7 PM"]),
        ("Cedar Garden grows sage.", ["Oak Garden grows sage"]),
        ("The museum does not open on Mondays.", ["The museum does open on Mondays"]),
        ("The museum opens on Mondays.", ["The museum does not open on Mondays"]),
        ("It opens on Tuesdays.", ["It", "museum opens Tuesdays"]),
        ("We grow rosemary and sage.", ["We grow rosemary or sage"]),
        ("We grow rosemary and sage.", ["We grow sage and rosemary"]),
        ("הגינה נפתחה בשנת 1990.", ["הגינה נפתחה בשנת 1991"]),
        ("גינת ארז מגדלת מרווה.", ["גינת אלון מגדלת מרווה"]),
        ("המוזיאון לא פתוח בימי שני.", ["המוזיאון פתוח בימי שני"]),
        ("היעד הוא לא רווח.", ["היעד", "רווח"]),
    ],
    ids=[
        "en-number",
        "en-name",
        "en-dropped-negation",
        "en-added-negation",
        "en-added-word",
        "en-changed-connective",
        "en-moved-words",
        "he-number",
        "he-name",
        "he-dropped-negation",
        "he-negation-after-copula",
    ],
)
def test_skipping_connectives_never_hides_a_changed_or_missing_word(sentence: str, texts):
    assert not claims_cover(sentence, claims(*texts))


def test_finding_quotes_the_draft_not_the_claim_text_that_skipped_a_word() -> None:
    draft = "The museum opens on Tuesdays."
    unsupported = {
        "text": "The museum opens Tuesdays",
        "kind": "factual",
        "supported": False,
        "contradicted": False,
        "evidence": [],
    }
    result = review("en", draft, [unsupported])
    assert result["findings"] == [
        {"code": "unsupported_claim", "sentence": draft, "claim": "The museum opens on Tuesdays"}
    ]
    assert result["sentences"][0]["claims"][0]["text"] == "The museum opens on Tuesdays"


@pytest.mark.parametrize(
    "quote,source,stored",
    [
        # SP-24: Terra ended an excerpt cut from a longer source sentence with ".".
        (
            "Cascade mentoring is a group model.",
            "Cascade mentoring is a group model in science training.",
            "Cascade mentoring is a group model",
        ),
        (
            "מודל המפל הוא מודל קבוצתי.",
            "מודל המפל הוא מודל קבוצתי בהכשרה מדעית.",
            "מודל המפל הוא מודל קבוצתי",
        ),
        ("שנהג לאכול בשר.", "נהג לאכול בשר בין פרוסות לחם", "נהג לאכול בשר"),
        ("We grow rosemary.", "We grow rosemary.", "We grow rosemary."),
    ],
    ids=["en-final-period", "he-final-period", "he-prefix-and-period", "exact"],
)
def test_quote_may_end_with_one_mark_the_source_lacks(quote: str, source: str, stored: str):
    assert matched_quote(quote, source) == stored


@pytest.mark.parametrize(
    "quote,source",
    [
        ("Meetings start at 7.", "Meetings start at 6 in the hall."),
        ("Oak Garden grows sage.", "Cedar Garden grows sage daily."),
        ("We grow rosemary..", "We grow rosemary in pots."),
        ("We grow. rosemary", "We grow rosemary"),
        ("!", "Admission is free"),
        ("הגינה נפתחה בשנת 1991.", "הגינה נפתחה בשנת 1990 בעיר."),
    ],
    ids=["number", "name", "two-marks", "inner-mark", "mark-only", "he-number"],
)
def test_quote_tolerance_never_accepts_changed_text(quote: str, source: str):
    assert matched_quote(quote, source) is None


def test_owner_call_to_action_is_not_an_instruction_to_the_ai() -> None:
    # SP-26: Terra blocked a draft that repeated the owner's own CTA from offer details.
    prompt = " ".join(REVIEW_SYSTEM.split())
    assert "instructions aimed at the AI" in prompt
    assert "that the owner wrote in the offer details" in prompt
    assert "repeating it is never copied_instructions" in prompt


def contact_review(draft: str, source: str, offer: str = "", cta: str = "") -> dict:
    verdict = {
        "issues": [],
        "blocking": [],
        "sentences": [
            {
                "index": 0,
                "claims": [
                    {
                        **sourced(draft.rstrip("."), draft.rstrip(".")),
                        "kind": "creative",
                        "supported": False,
                        "evidence": [],
                    }
                ],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        return review_draft(
            draft,
            [{"chunk_id": "source", "content": source}],
            {},
            {"language": "en", "cta": cta},
            offer_details=offer,
        )


SOURCE_WITH_CONTACTS = (
    "To join, message @cedar_signup, call 050-1234567, write to join@cedar.example "
    "or visit https://cedar.example/join. Founded 2026-10-29."
)


@pytest.mark.parametrize(
    "draft,detail",
    [
        ("Message @cedar_signup to join.", "@cedar_signup"),
        ("Call 050-1234567 to join.", "050-1234567"),
        ("Write to join@cedar.example today.", "join@cedar.example"),
        ("Visit https://cedar.example/join.", "https://cedar.example/join"),
        ("Call 050 123 4567 to join.", "050 123 4567"),
    ],
    ids=["handle", "phone", "email", "link", "phone-other-format"],
)
def test_contact_detail_taken_from_a_source_is_a_finding(draft: str, detail: str) -> None:
    # SP-26: a planted source can send readers to its own contact details. Deterministic,
    # so it does not depend on the reviewer noticing.
    result = contact_review(draft, SOURCE_WITH_CONTACTS)
    assert result["status"] == "checked"
    assert result["findings"] == [
        {"code": "source_contact_detail", "sentence": draft, "claim": detail}
    ]


@pytest.mark.parametrize(
    "draft,offer,cta",
    [
        # The owner's own details may be repeated.
        ("Message @cedar_signup to join.", "Message @cedar_signup with GARDEN.", ""),
        ("Call 050-1234567 to join.", "", "Invite readers to call 050 1234567."),
        # Not in any source: an unsupported claim for the reviewer, not this finding.
        ("Message @other_handle to join.", "", ""),
        # Dates and years are not phone numbers.
        ("Founded 2026-10-29.", "", ""),
    ],
    ids=["owner-offer", "owner-cta", "not-in-sources", "date"],
)
def test_owner_details_and_numbers_are_not_source_contact_findings(draft, offer, cta) -> None:
    result = contact_review(draft, SOURCE_WITH_CONTACTS, offer, cta)
    assert [f["code"] for f in result["findings"]] == []


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("The treatment is ineffective.", ["The treatment is effective"]),
        ("Most patients are asymptomatic.", ["Most patients are symptomatic"]),
        ("The update will bypass security review.", ["The update will pass security review"]),
        ("Tickets cost €5.", ["Tickets cost $5"]),
        ("Class size ≤ 10 students.", ["Class size ≥ 10 students"]),
        ("המנטורים ממליצים עליהם.", ["המנטורים ממליצים עלי"]),
        # Already possible in v6 by splitting the word across two claims.
        ("The treatment is ineffective.", ["The treatment is", "effective"]),
        # A sign that changes a fact may not stay outside every claim.
        ("Tickets cost €5.", ["Tickets cost", "5"]),
        ("Half the plots, 50%, are taken.", ["Half the plots", "50", "are taken"]),
        ("The garden opens at 9:00 ≥ daily.", ["The garden opens at 9", "00", "daily"]),
    ],
    ids=[
        "part-of-word-in",
        "part-of-word-a",
        "part-of-word-by",
        "changed-currency",
        "changed-comparison",
        "he-part-of-word",
        "v6-split-word",
        "currency-outside",
        "percent-outside",
        "comparison-outside",
    ],
)
def test_claim_cannot_split_a_draft_word_or_change_a_symbol(sentence: str, texts: list[str]):
    assert not claims_cover(sentence, claims(*texts))


@pytest.mark.parametrize(
    "sentence,texts",
    [
        ("Tickets cost €5.", ["Tickets cost €5"]),
        ("Join us — we meet weekly! 🌿", ["Join us", "we meet weekly"]),
        ("ג'ון מונטגיו נהג לאכול בשר.", ["ג'ון מונטגיו נהג לאכול בשר"]),
        ("צה״ל הוקם ב-1948.", ["צה״ל הוקם ב-1948"]),
        ("מַלְכָּה גרה בארמון.", ["מַלְכָּה גרה בארמון"]),
    ],
    ids=["sign-inside-claim", "dash-and-emoji-outside", "geresh", "gershayim", "vowel-points"],
)
def test_signs_inside_claims_and_plain_punctuation_outside_them_pass(sentence, texts):
    assert claims_cover(sentence, claims(*texts))


def test_long_claims_are_matched_in_one_pass() -> None:
    # A review steered into one-word steps over a long sentence must not stall the API.
    sentence = ", ".join(["a"] * 800) + "."
    assert claims_cover(sentence, claims(" ".join(["a"] * 800)))
    assert not claims_cover(sentence + " Today.", claims(" ".join(["a"] * 800)))


@pytest.mark.parametrize(
    "quote,source",
    [
        ("Meetings start at 1.", "Meetings start at 10 in the hall."),
        ("The museum is open.", "The museum is opening in 2027."),
        ("Is parking free.", "Is parking free? No."),
        ("נהג לאכול.", "נהג לאכולת הבוקר"),
        # The prefix tolerance must leave a whole source word.
        ("מנהג", "זה מנהג עתיק"),
        ("שנהג", "זה מנהג עתיק"),
        (".", "We grow rosemary."),
        (" ", "We grow rosemary."),
    ],
    ids=[
        "cut-number",
        "cut-word",
        "replaced-mark",
        "he-cut-word",
        "exact-word",
        "prefix-inside-word",
        "mark-only-exact",
        "space-only",
    ],
)
def test_quote_tolerances_keep_word_boundaries(quote: str, source: str):
    if quote == "מנהג":
        # An exact quote is still exact.
        assert matched_quote(quote, source) == quote
        return
    assert matched_quote(quote, source) is None
