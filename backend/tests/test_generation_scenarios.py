"""Offline validation of live-evaluation fixtures and deterministic output checks."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from scripts.generation_scenarios import check_content, load_scenarios


def fixture_rows() -> list[dict[str, object]]:
    path = Path(__file__).parents[1] / "scripts" / "generation_scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_matrix_has_all_sixteen_cases():
    cases = load_scenarios()
    assert len(cases) == 16
    assert len({(case.domain, case.category, case.language) for case in cases}) == 16
    assert {case.platform for case in cases} == {"linkedin", "facebook"}


@pytest.mark.parametrize("raw", [None, [], {}, "cases", [None]])
def test_loader_rejects_null_empty_or_wrong_shape(raw: object):
    with patch.object(Path, "read_text", return_value=json.dumps(raw)):
        with pytest.raises((ValueError, ValidationError)):
            load_scenarios()


def test_loader_rejects_duplicate_names():
    rows = fixture_rows()
    rows.append(rows[0].copy())
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises(ValueError, match="unique"):
            load_scenarios()


def test_loader_rejects_missing_coverage():
    rows = fixture_rows()[:-1]
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises(ValueError, match="Each domain"):
            load_scenarios()


@pytest.mark.parametrize("terms", [[], [""], [" \t"], [None]])
def test_loader_rejects_invalid_required_terms(terms: object):
    rows = fixture_rows()
    rows[0]["required_terms"] = terms
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises(ValueError):
            load_scenarios()


@pytest.mark.parametrize("patterns", [[], [""], [" "], ["a*"], ["["], [None]])
def test_loader_rejects_invalid_patterns(patterns: object):
    rows = fixture_rows()
    rows[0]["forbidden_patterns"] = patterns
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises((ValueError, re.error)):
            load_scenarios()


@pytest.mark.parametrize("index", range(16))
def test_all_cases_accept_only_sourced_required_terms(index: int):
    case = load_scenarios()[index]
    check_content(case, " ".join(case.required_terms).upper())


@pytest.mark.parametrize(
    "content", ["", " \n", "books", "books reading room #local", "books reading room " + "x" * 600]
)
def test_content_rejects_missing_facts_and_presentation_failures(content: str):
    case = load_scenarios()[0]
    with pytest.raises(AssertionError):
        check_content(case, content)


@pytest.mark.parametrize(
    "claim",
    [
        "37 dollars",
        "thirty-seven dollars",
        "May 14",
        "improves reading scores",
        "forty percent",
        "guaranteed success",
        "שלושים ושבעה",
        "משפר ציונים",
    ],
)
def test_content_rejects_prompted_unsupported_claims(claim: str):
    case = load_scenarios()[0]
    with pytest.raises(AssertionError, match="Unsupported fixture detail"):
        check_content(case, "books reading room " + claim)


def test_exact_length_limit():
    case = load_scenarios()[0]
    base = "books reading room "
    check_content(case, base + "x" * (600 - len(base)))
    with pytest.raises(AssertionError, match="overlong"):
        check_content(case, base + "x" * (601 - len(base)))


@pytest.mark.parametrize("arguments", [[], ["--validate-cases"]])
def test_cli_defaults_to_offline_validation(arguments: list[str]):
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "scripts" / "evaluate_generation.py"
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        env={},
        check=True,
    )
    review_cases = Path(__file__).parents[1] / "scripts" / "generation_review_cases.json"
    assert json.loads(result.stdout) == {
        "validated_cases": len(json.loads(review_cases.read_text(encoding="utf-8"))),
        "generation_scenarios": 16,
        "provider_calls": 0,
    }


@pytest.mark.parametrize(
    "arguments", [["--scenarios-only"], ["--isolated"], ["--validate-cases", "--scenarios-only"]]
)
def test_cli_rejects_execution_selectors_without_live(arguments: list[str]):
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "scripts" / "evaluate_generation.py"
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        env={},
        check=False,
    )
    assert result.returncode == 2
    assert "require --live" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize(
    ("run_status", "visible_status", "visible_result", "save_status", "failure"),
    [
        ("Failed", "Failed", None, 404, None),
        ("Completed", "Failed", None, 404, "not marked Failed"),
        ("Failed", "Completed", None, 404, "remains visible"),
        ("Failed", "Failed", {"content": "leak"}, 404, "remains visible"),
        ("Failed", "Failed", None, 201, "remains saveable"),
    ],
)
def test_rejected_run_checks_and_source_cleanup(
    run_status: str,
    visible_status: str,
    visible_result: object,
    save_status: int,
    failure: str | None,
):
    from unittest.mock import MagicMock
    from uuid import uuid4

    import httpx
    from fastapi.testclient import TestClient

    from scripts.generation_scenarios import run_scenarios

    case = load_scenarios()[2]
    client = MagicMock(spec=TestClient)
    client.get.side_effect = [
        httpx.Response(200, json={"version": 0}),
        httpx.Response(200, json={"status": visible_status, "result": visible_result}),
    ]
    client.put.return_value = httpx.Response(200, json={"version": 1})
    client.post.side_effect = [
        httpx.Response(409, json={"error": {"message": "grounding_review_failed"}}),
        httpx.Response(save_status),
    ]
    client.delete.return_value = httpx.Response(200)
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value.scalar.return_value = MagicMock(
        status=run_status, id=uuid4()
    )
    with (
        patch("scripts.generation_scenarios.prepare_source", return_value="fixture-document"),
        patch("app.db.SessionLocal", session_factory),
    ):
        if failure is None:
            run_scenarios(client, [case])
        else:
            with pytest.raises(AssertionError, match=failure):
                run_scenarios(client, [case])
    client.delete.assert_called_once_with("/knowledge/fixture-document")


def test_loader_rejects_duplicate_matrix_entry_with_unique_name():
    rows = fixture_rows()
    duplicate = rows[0].copy()
    duplicate["name"] = "extra_unique_name"
    rows.append(duplicate)
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises(ValueError, match="Each domain"):
            load_scenarios()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--scenario", "repair_missing_price_he"],
        ["--scenario", "repair_missing_price_he", "--scenario", "library_supported_en"],
    ],
)
def test_named_scenarios_require_live(arguments: list[str]):
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "scripts" / "evaluate_generation.py"
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        env={},
        check=False,
    )
    assert result.returncode == 2
    assert "require --live" in result.stderr
    assert not result.stdout


def test_unknown_scenario_rejected_before_live_setup():
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "scripts" / "evaluate_generation.py"
    result = subprocess.run(
        [sys.executable, str(script), "--live", "--scenario", "unknown_case"],
        capture_output=True,
        text=True,
        env={},
        check=False,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert not result.stdout


def test_selected_names_propagate_to_isolated_child_without_calls():
    import runpy
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    script = Path(__file__).parents[1] / "scripts" / "evaluate_generation.py"
    with patch.object(sys, "path", [str(script.parent), *sys.path]):
        namespace = runpy.run_path(str(script), run_name="offline_selector_test")
    engine = MagicMock()
    engine.dialect.identifier_preparer.quote.return_value = '"fixture_runtime"'
    settings = SimpleNamespace(
        migration_database_url="postgresql+psycopg://fixture_admin@localhost/fixture",
        database_url="postgresql+psycopg://fixture_runtime@localhost/fixture",
    )
    selected = ["repair_missing_price_he", "library_supported_en"]
    with (
        patch("sqlalchemy.create_engine", return_value=engine),
        patch("app.config.get_settings", return_value=settings),
        patch("subprocess.run") as subprocess_run,
    ):
        namespace["isolated_database"](True, selected)
    assert subprocess_run.call_count == 2
    child_arguments = subprocess_run.call_args_list[1].args[0]
    assert child_arguments[2:] == [
        "--live",
        "--isolated",
        "--scenarios-only",
        "--scenario",
        selected[0],
        "--scenario",
        selected[1],
    ]
    assert engine.dispose.call_count == 2


def test_exact_reviewed_hebrew_disclaimer_is_allowed_after_sourced_facts():
    case = next(case for case in load_scenarios() if case.name == "repair_missing_price_he")
    check_content(
        case,
        "סדנת תיקוני הנמל מתקנת אופניים ומפעילה עמדת השאלת כלים. "
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים.",
    )


@pytest.mark.parametrize(
    "claim",
    [
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים. המחיר הוא שלושים ושבעה שקלים.",
        "יש מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים.",
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים. המחיר הוא 37 שקלים.",
        "הודעה: אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים.",
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים, אבל זה המחיר בפועל.",
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים. והמחיר מובטח.",
        "אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים.המחיר נכון.",
    ],
)
def test_disclaimer_exemption_cannot_hide_claims_or_extra_clauses(claim: str):
    case = next(case for case in load_scenarios() if case.name == "repair_missing_price_he")
    with pytest.raises(AssertionError, match="Unsupported fixture detail"):
        check_content(case, "אופניים וכלים. " + claim)


@pytest.mark.parametrize("disclaimers", [None, [None], [""], [" \t"]])
def test_loader_rejects_null_or_blank_disclaimers(disclaimers: object):
    rows = fixture_rows()
    rows[0]["allowed_disclaimers"] = disclaimers
    with patch.object(Path, "read_text", return_value=json.dumps(rows)):
        with pytest.raises(ValueError):
            load_scenarios()


def test_disclaimer_exemption_is_specific_to_reviewed_case():
    case = next(case for case in load_scenarios() if case.name == "library_missing_price_he")
    with pytest.raises(AssertionError, match="Unsupported fixture detail"):
        check_content(
            case,
            "ספרים וחדר קריאה. אין מידע זמין לגבי מחיר כניסה של שלושים ושבעה שקלים.",
        )


def test_exact_reviewed_english_date_disclaimer_is_allowed():
    case = next(case for case in load_scenarios() if case.name == "repair_missing_date_en")
    check_content(
        case,
        "Harbor Repair Workshop repairs bicycles and operates a tool-lending desk. "
        "Details about a special event on May 14, 2030, are not available in the provided sources.",
    )


@pytest.mark.parametrize(
    "additional_claim",
    [
        " The event is on May 14, 2030.",
        " The event is on May fourteen.",
        " This improves bicycle lifespan.",
    ],
)
def test_date_disclaimer_does_not_hide_additional_claim(additional_claim: str):
    case = next(case for case in load_scenarios() if case.name == "repair_missing_date_en")
    with pytest.raises(AssertionError, match="Unsupported fixture detail"):
        check_content(
            case,
            "Harbor Repair Workshop repairs bicycles and operates a tool-lending desk. "
            "Details about a special event on May 14, 2030, "
            "are not available in the provided sources." + additional_claim,
        )


def test_aggregator_runs_remaining_cases_and_preserves_all_failures():
    from unittest.mock import MagicMock, call

    from fastapi.testclient import TestClient

    from scripts.generation_scenarios import run_scenarios

    client = MagicMock(spec=TestClient)
    cases = load_scenarios()[:3]
    with patch(
        "scripts.generation_scenarios.run_scenario",
        side_effect=[AssertionError("first failed"), None, AssertionError("third failed")],
    ) as run:
        with pytest.raises(AssertionError, match="first failed; third failed"):
            run_scenarios(client, cases)
    assert run.call_args_list == [call(client, case) for case in cases]


def test_aggregator_does_not_convert_runtime_errors_to_passes():
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from scripts.generation_scenarios import run_scenarios

    client = MagicMock(spec=TestClient)
    with patch("scripts.generation_scenarios.run_scenario", side_effect=RuntimeError("broken")):
        with pytest.raises(RuntimeError, match="broken"):
            run_scenarios(client, load_scenarios()[:2])


def test_exact_reviewed_hebrew_date_disclaimer_is_allowed():
    case = next(case for case in load_scenarios() if case.name == "repair_missing_date_he")
    check_content(
        case,
        "סדנת תיקוני הנמל מתקנת אופניים ומפעילה עמדת השאלת כלים. "
        "אין לנו מידע על אירוע מיוחד בארבעה עשר במאי 2030.",
    )


def test_hebrew_date_disclaimer_does_not_hide_appended_factual_date():
    case = next(case for case in load_scenarios() if case.name == "repair_missing_date_he")
    with pytest.raises(AssertionError, match="Unsupported fixture detail"):
        check_content(
            case,
            "סדנת תיקוני הנמל מתקנת אופניים ומפעילה עמדת השאלת כלים. "
            "אין לנו מידע על אירוע מיוחד בארבעה עשר במאי 2030. "
            "האירוע יתקיים בארבעה עשר במאי 2030.",
        )
