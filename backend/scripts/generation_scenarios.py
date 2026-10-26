"""Typed fixtures and checks for opt-in multi-domain generation evaluation."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    domain: Literal["library", "repair"]
    category: Literal["supported", "missing_price", "missing_date", "missing_benefit"]
    language: Literal["en", "he"]
    platform: Literal["linkedin", "facebook"]
    brand: str = Field(min_length=1)
    source: str = Field(min_length=1)
    topic: str = Field(min_length=1, max_length=2000)
    required_terms: list[str] = Field(min_length=1)
    forbidden_patterns: list[str] = Field(min_length=1)
    allowed_disclaimers: list[str] = Field(default_factory=list)


def load_scenarios() -> list[Scenario]:
    path = Path(__file__).with_name("generation_scenarios.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Generation scenarios must be a nonempty array")
    scenarios = [Scenario.model_validate(item) for item in raw]
    if len({case.name for case in scenarios}) != len(scenarios):
        raise ValueError("Generation scenario names must be unique")
    required = {
        (domain, category, language)
        for domain in ("library", "repair")
        for category in ("supported", "missing_price", "missing_date", "missing_benefit")
        for language in ("en", "he")
    }
    if (
        len(scenarios) != len(required)
        or {(case.domain, case.category, case.language) for case in scenarios} != required
    ):
        raise ValueError("Each domain requires supported and missing-fact cases in EN/HE")
    for case in scenarios:
        if any(not term.strip() for term in case.required_terms):
            raise ValueError("Required terms must not be blank")
        if any(not sentence.strip() for sentence in case.allowed_disclaimers):
            raise ValueError("Allowed disclaimers must be complete nonempty sentences")
        for pattern in case.forbidden_patterns:
            if not pattern.strip() or re.search(pattern, "") is not None:
                raise ValueError("Forbidden patterns must not match empty content")
            re.compile(pattern, re.IGNORECASE)
    return scenarios


def check_content(case: Scenario, content: str) -> None:
    if not content.strip() or len(content) > 600 or "#" in content:
        raise AssertionError("Empty, overlong or hashtagged output: " + case.name)
    if not all(term.casefold() in content.casefold() for term in case.required_terms):
        raise AssertionError("Missing required sourced facts: " + case.name)
    # Only exact, manually reviewed full sentences are exempt; never strip a negation prefix.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", content)
    claims = "\n".join(
        sentence for sentence in sentences if sentence.strip() not in case.allowed_disclaimers
    )
    if any(re.search(pattern, claims, re.IGNORECASE) for pattern in case.forbidden_patterns):
        raise AssertionError("Unsupported fixture detail: " + case.name)


def prepare_source(client: "TestClient", case: Scenario) -> str:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import IngestionJob
    from app.worker import embed_document, process_text

    with patch("app.knowledge.process_text.apply_async"):
        added = client.post("/knowledge/text", json={"title": case.name, "text": case.source})
    if added.status_code != 202:
        raise AssertionError("Source creation failed: " + case.name)
    document_id = UUID(added.json()["id"])
    with SessionLocal() as session:
        job = session.scalar(
            select(IngestionJob.id).where(
                IngestionJob.document_id == document_id, IngestionJob.kind == "text_ingestion"
            )
        )
    if job is None:
        raise AssertionError("Missing preparation job: " + case.name)
    process_text(str(job))
    with patch("app.worker.embed_document.apply_async"):
        queued = client.post(f"/knowledge/{document_id}/embed")
    if queued.status_code != 202:
        raise AssertionError("Embedding enqueue failed: " + case.name)
    with SessionLocal() as session:
        job = session.scalar(
            select(IngestionJob.id).where(
                IngestionJob.document_id == document_id, IngestionJob.kind == "embedding"
            )
        )
    if job is None:
        raise AssertionError("Missing embedding job: " + case.name)
    embed_document(str(job))
    configuration = client.get("/generation/configuration")
    if configuration.status_code != 200 or configuration.json()["ready_documents"] != 1:
        raise AssertionError("Scenario requires exactly one Ready source: " + case.name)
    return str(document_id)


def run_scenarios(client: "TestClient", scenarios: list[Scenario]) -> None:
    failures: list[str] = []
    for case in scenarios:
        try:
            run_scenario(client, case)
        except AssertionError as exc:
            failures.append(str(exc))
            print(
                json.dumps({"scenario": case.name, "passed": False, "error": str(exc)}), flush=True
            )
    if failures:
        raise AssertionError("Generation scenario failures: " + "; ".join(failures))


def run_scenario(client: "TestClient", case: Scenario) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import GenerationRun

    current = client.get("/brand")
    if current.status_code != 200:
        raise AssertionError("Cannot load evaluation brand")
    brand = current.json()
    updated = client.put(
        "/brand",
        json={
            "name": case.brand,
            "voice": "Specific, plain language. No hashtags or emojis.",
            "audience": "Local residents",
            "guidelines": "Use only source facts. Omit details missing from sources.",
            "prohibited_claims": "Guaranteed results; הבטחת תוצאות",
            "version": brand["version"] if brand is not None else 0,
        },
    )
    if updated.status_code != 200:
        raise AssertionError("Brand setup failed: " + case.name)
    document_id = prepare_source(client, case)
    try:
        request_key = uuid4()
        response = client.post(
            "/generation",
            json={
                "request_key": str(request_key),
                "platform": case.platform,
                "language": case.language,
                "topic": case.topic,
                "length": "short",
                "goal": "Share source facts; omit unavailable details without invention",
            },
        )
        if response.status_code != 200:
            message = response.json().get("error", {}).get("message")
            if (
                case.category == "supported"
                or response.status_code != 409
                or message not in {"grounding_review_failed", "insufficient_grounding"}
            ):
                raise AssertionError(f"Unexpected generation failure: {case.name}: {message}")
            with SessionLocal() as session:
                run = session.scalar(
                    select(GenerationRun).where(GenerationRun.request_key == request_key)
                )
                if run is None or run.status != "Failed":
                    raise AssertionError("Rejected run was not marked Failed: " + case.name)
                run_id = str(run.id)
            status = client.get("/generation/" + run_id)
            if (
                status.status_code != 200
                or status.json()["result"] is not None
                or status.json()["status"] != "Failed"
            ):
                raise AssertionError("Rejected draft remains visible: " + case.name)
            save = client.post(
                "/posts",
                json={
                    "save_key": str(uuid4()),
                    "generation_run_id": run_id,
                    "platform": case.platform,
                    "language": case.language,
                    "content": "Rejected evaluation draft",
                },
            )
            if save.status_code != 404:
                raise AssertionError("Rejected draft remains saveable: " + case.name)
            print(
                json.dumps(
                    {
                        "scenario": case.name,
                        "outcome": "withheld",
                        "reason": message,
                        "passed": True,
                    }
                ),
                flush=True,
            )
            return
        result = response.json()
        try:
            check_content(case, result["content"])
        except AssertionError:
            # This runner contains disposable fixtures only, never user workspace content.
            print(
                json.dumps(
                    {"scenario": case.name, "diagnostic_content": result["content"]},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            raise
        if (
            not result["grounded"]
            or result["metadata"]["grounding_review"]["status"] != "passed"
            or result["metadata"]["brand_version"] != updated.json()["version"]
            or {source["document_id"] for source in result["sources"]} != {document_id}
        ):
            raise AssertionError("Invalid generation provenance: " + case.name)
        saved = client.post(
            "/posts",
            json={
                "save_key": str(uuid4()),
                "generation_run_id": result["id"],
                "platform": case.platform,
                "language": case.language,
                "content": result["content"],
            },
        )
        if saved.status_code != 201:
            raise AssertionError("Draft save failed: " + case.name)
        draft_id = saved.json()["id"]
        read = client.get("/posts/" + draft_id)
        if read.status_code != 200 or read.json()["content"] != result["content"]:
            raise AssertionError("Draft round-trip failed: " + case.name)
        if client.delete("/posts/" + draft_id).status_code != 200:
            raise AssertionError("Draft cleanup failed: " + case.name)
        print(
            json.dumps(
                {
                    "scenario": case.name,
                    "outcome": "supported_draft",
                    "passed": True,
                    "model": result["metadata"]["model"],
                    "cost_usd": result["metadata"]["total_cost_usd"],
                }
            ),
            flush=True,
        )
    finally:
        if client.delete("/knowledge/" + document_id).status_code != 200:
            raise AssertionError("Source cleanup failed: " + case.name)
