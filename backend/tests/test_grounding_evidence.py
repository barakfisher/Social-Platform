import json
from unittest.mock import patch

import pytest

from app.generation_provider import GenerationError
from app.grounding import REVIEW_VERSION, review_draft


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
                "supported": True,
                "evidence": [{"chunk_id": "source", "quote": quote} for quote in quotes],
            }
        ],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        if quote_mode == "separate":
            result = review_draft(
                draft, [{"chunk_id": "source", "content": source}], {}, {"language": language}
            )
            assert result["version"] == REVIEW_VERSION == "source-review-v3"
            assert result["sentences"][0]["evidence"] == verdict["sentences"][0]["evidence"]
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
        ([{"chunk_id": "source", "quote": "We grow rosemary. Admission is free."}], "failed"),
        ([{"chunk_id": "other", "quote": "We grow rosemary."}], "failed"),
        ([{"chunk_id": "source", "quote": None}], "invalid"),
        ([{"chunk_id": None, "quote": "We grow rosemary."}], "invalid"),
        ([{"chunk_id": "source", "quote": ""}], "invalid"),
        ([{"chunk_id": "source"}], "invalid"),
        ([], "invalid"),
        (None, "invalid"),
    ],
)
def test_evidence_boundaries_fail_closed(evidence: object, error: str) -> None:
    verdict = {
        "accepted": True,
        "issues": [],
        "sentences": [{"index": 0, "supported": True, "evidence": evidence}],
    }
    with patch("app.grounding.chat_completion", return_value=(json.dumps(verdict), {})):
        with pytest.raises(GenerationError, match=f"^grounding_review_{error}$"):
            review_draft(
                "We grow rosemary.",
                [{"chunk_id": "source", "content": "We grow rosemary."}],
                {},
                {"language": "en"},
            )
