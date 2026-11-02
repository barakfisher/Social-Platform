"""Measure draft length and depth on the owner's own topics, read-only (SP-28).

Paid: one writer call and one source check per topic, on that topic's latest Ready inputs
with the same writer and reviewer models. A call whose worst case would pass what is left
of --max-usd is refused before it is sent, and the report keeps every draft measured so far.

    uv run python scripts/measure_draft_quality.py --max-usd 0.80 --out v9.json
    uv run python scripts/measure_draft_quality.py --max-usd 0.80 --baseline-ref main
    uv run python scripts/measure_draft_quality.py --max-usd 0.10 --writer-only --topic "What"

--baseline-ref measures the writer prompt of another git revision with today's retrieval
and source check. Every database transaction is READ ONLY: the script stores nothing.
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
import types
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Findings that count as a claim the sources do not support.
UNSUPPORTED_CODES = ("unsupported_claim", "contradicted_claim")
TOPIC_PREVIEW = 60


class Stop(Exception):
    """Ends the run early; the drafts measured so far are still reported."""


# Report computations (hermetic tests: tests/test_measure_draft_quality.py)


def latest_inputs(runs: list[tuple[object, dict]]) -> list[dict]:
    """The latest Ready inputs of each topic, oldest topic first (ties by topic, so a rerun
    measures in the same order); runs are (created_at, inputs) in any order."""
    latest: dict[str, tuple[object, dict]] = {}
    for created_at, inputs in runs:
        topic = inputs["topic"]
        if topic not in latest or created_at > latest[topic][0]:
            latest[topic] = (created_at, inputs)
    ordered = sorted(latest.values(), key=lambda item: (item[0], item[1]["topic"]))
    return [inputs for _, inputs in ordered]


def length_status(characters: int, minimum: int, maximum: int, warned: bool) -> str:
    if characters > maximum:
        return "over"
    if characters >= minimum:
        return "in_range"
    return "short_warned" if warned else "short"


def draft_row(
    inputs: dict,
    *,
    minimum: int,
    maximum: int,
    content: str,
    warnings: list[str],
    sources: list[dict],
    cited_ids: list[str],
    review: dict,
    cost_usd: float | None,
    seconds: float,
) -> dict:
    cited = [source for source in sources if source["chunk_id"] in set(cited_ids)]
    checked = review.get("status") == "checked"
    return {
        "topic": inputs["topic"][:TOPIC_PREVIEW],
        "length": inputs["length"],
        "characters": len(content),
        "words": len(content.split()),
        "target": [minimum, maximum],
        "status": length_status(len(content), minimum, maximum, bool(warnings)),
        "warnings": warnings,
        "received_chunks": len(sources),
        "received_documents": len({source["document_id"] for source in sources}),
        "cited_chunks": len(cited),
        "cited_documents": len({source["document_id"] for source in cited}),
        "review": review.get("status"),
        "unsupported": (
            sum(f["code"] in UNSUPPORTED_CODES for f in review.get("findings", []))
            if checked
            else None
        ),
        "cost_usd": cost_usd,
        "seconds": round(seconds, 1),
        "content": content,
    }


def summary(rows: list[dict], failures: list[dict]) -> dict:
    checked = [row["unsupported"] for row in rows if row["unsupported"] is not None]
    costs = [row["cost_usd"] for row in rows]
    return {
        "drafts": len(rows),
        "in_range": sum(row["status"] == "in_range" for row in rows),
        "short_warned": sum(row["status"] == "short_warned" for row in rows),
        "short_unwarned": sum(row["status"] == "short" for row in rows),
        "median_characters": statistics.median(r["characters"] for r in rows) if rows else None,
        "median_cited_chunks": statistics.median(r["cited_chunks"] for r in rows) if rows else None,
        "checked_drafts": len(checked),
        "mean_unsupported_per_checked": statistics.mean(checked) if checked else None,
        "failures": failures,
        "cost_usd": sum(costs) if rows and all(c is not None for c in costs) else None,
    }


def writer_message(
    brand: dict, preferences: dict, sources: list[dict], limit: int, target: dict | None
) -> str:
    """The writer's data, as app.generation sends it; no length target (short drafts, or a
    baseline without targets) sends none."""
    data = {
        "brand": brand,
        "preferences": preferences,
        "sources": sources,
        "platform_character_limit": limit,
    }
    if target is not None:
        data["length_target"] = target
    return json.dumps(data, ensure_ascii=False)


def cost(metadata: dict) -> float | None:
    return (metadata.get("usage") or {}).get("cost_usd")


# Live run


def read_only(engine) -> None:
    """Every transaction on engine's connections is READ ONLY in PostgreSQL itself."""
    from sqlalchemy import event

    engine.dispose()

    @event.listens_for(engine, "connect")
    def _read_only(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute("SET default_transaction_read_only = on")
        connection.commit()


def writer_systems(ref: str | None) -> tuple[Callable, str, Callable]:
    """(writer prompt for a level and length, prompt version, length target for a length) for
    the checkout, or for app/generation.py at ref."""
    import app.generation as current

    if ref is None:
        return current.writer_system, current.PROMPT_VERSION, current.length_target
    source = subprocess.run(
        ["git", "show", f"{ref}:backend/app/generation.py"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    module = types.ModuleType(f"baseline_generation_{ref}")
    exec(compile(source, f"{ref}:app/generation.py", "exec"), module.__dict__)
    system = getattr(module, "writer_system", lambda level, _length: module.WRITER_SYSTEMS[level])
    target = getattr(module, "length_target", lambda _length: None)
    return system, module.PROMPT_VERSION, target


def failure(topic: str, code: str, metadata: dict | None = None, content: str = "") -> dict:
    """What a failed topic cost in tokens and, for a draft over its limit, by how much."""
    found: dict = {"topic": topic, "code": code}
    if metadata and metadata.get("usage"):
        found["usage"] = metadata["usage"]
    if content:
        found["characters"], found["words"] = len(content), len(content.split())
    return found


def chosen(topics: list[dict], prefixes: list[str] | None) -> list[dict]:
    if not prefixes:
        return topics
    return [t for t in topics if any(t["topic"].startswith(p) for p in prefixes)]


def measure(
    max_usd: float,
    ref: str | None,
    topic_prefixes: list[str] | None = None,
    writer_only: bool = False,
) -> dict:
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import SessionLocal, engine
    from app.embeddings import EmbeddingError, embed_texts
    from app.generation import (
        LENGTH_LIMITS,
        LENGTH_TARGET_MINIMUMS,
        Completion,
        GenerateInput,
        bounded_context,
        brand_constraints,
    )
    from app.generation_provider import GenerationError, chat_completion, generation_key
    from app.grounding import check_draft
    from app.grounding import prompt_tokens as generation_tokens
    from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID
    from app.models import BrandDNA, GenerationRun
    from app.retrieval import relevant_context
    from app.writer_models import provider_tokens, writer_output_tokens, writer_profile

    read_only(engine)
    settings = get_settings()
    system_for, version, target_for = writer_systems(ref)
    rows: list[dict] = []
    failures: list[dict] = []
    report = {"prompt_version": version, "max_usd": max_usd, "rows": rows, "stopped": None}
    spent = 0.0
    try:
        if not generation_key():
            raise Stop("no generation key is configured")
        with SessionLocal() as session:
            brand_row = session.scalar(
                select(BrandDNA).where(
                    BrandDNA.user_id == LOCAL_USER_ID,
                    BrandDNA.workspace_id == LOCAL_WORKSPACE_ID,
                )
            )
            runs = session.execute(
                select(GenerationRun.created_at, GenerationRun.inputs).where(
                    GenerationRun.user_id == LOCAL_USER_ID,
                    GenerationRun.workspace_id == LOCAL_WORKSPACE_ID,
                    GenerationRun.status == "Ready",
                )
            ).all()
        if brand_row is None:
            raise Stop("no Brand DNA")
        brand = brand_constraints(brand_row)
        topics = latest_inputs([(created_at, inputs) for created_at, inputs in runs])
        if not topics:
            raise Stop("no Ready drafts to take topics from")
        topics = chosen(topics, topic_prefixes)
        if not topics:
            raise Stop("no topic starts with a --topic value")
        for inputs in topics:
            started = time.monotonic()
            payload = GenerateInput(**inputs, request_key=uuid4())
            writer_model = payload.writer_model or settings.generation_model
            review_model = payload.review_model or settings.generation_review_model
            profile = writer_profile(writer_model)
            preferences = payload.writer_preferences()
            try:
                vector = embed_texts([payload.topic])[0]
            except EmbeddingError as exc:
                # Every topic needs one; a refused key or a spent provider limit ends the run.
                raise Stop(f"the topic could not be embedded ({exc})") from None
            with SessionLocal() as session:
                found = relevant_context(
                    session,
                    vector,
                    user_id=LOCAL_USER_ID,
                    workspace_id=LOCAL_WORKSPACE_ID,
                    max_distance=settings.generation_max_distance,
                )
            sources = bounded_context(found, settings.generation_context_budget)
            topic = payload.topic[:TOPIC_PREVIEW]
            if not sources:
                failures.append({"topic": topic, "code": "insufficient_context"})
                continue
            system = system_for(payload.knowledge_level, payload.length)
            target = target_for(payload.length)
            user = writer_message(
                brand, preferences, sources, LENGTH_LIMITS[payload.length], target
            )
            tokens = generation_tokens(system) + generation_tokens(user) + 32
            if tokens > settings.generation_prompt_budget:
                failures.append({"topic": topic, "code": "generation_prompt_limit"})
                continue
            try:
                raw, metadata = chat_completion(
                    system,
                    user,
                    provider_tokens(tokens, profile),
                    budget_usd=max_usd - spent,
                    output_tokens=writer_output_tokens(profile),
                    model_id=writer_model,
                )
            except GenerationError as exc:
                if exc.code == "generation_spending_limit":
                    raise Stop("the next writer call could pass --max-usd") from None
                spent += cost(exc.metadata) or 0.0
                failures.append(failure(topic, exc.code, exc.metadata))
                continue
            spent += cost(metadata) or 0.0
            completion = Completion.model_validate_json(raw)
            content = completion.content.strip()
            if len(content) > LENGTH_LIMITS[payload.length]:
                failures.append(failure(topic, "generation_output_limit", metadata, content))
                continue
            if writer_only:
                review = {"status": "not_requested", "reason": None, "findings": []}
                review_cost: float | None = 0.0
            else:
                # As the source check on request (app.recheck): the cited chunks, or every chunk
                # the writer received when it cited none.
                by_id = {source["chunk_id"]: source for source in sources}
                references = [
                    by_id[i] for i in dict.fromkeys(completion.source_ids) if i in by_id
                ] or sources
                try:
                    review = check_draft(
                        content,
                        references,
                        brand,
                        preferences,
                        offer_details=payload.offer_details,
                        budget_usd=max_usd - spent,
                        model_id=review_model,
                    )
                except GenerationError as exc:
                    spent += cost(exc.metadata) or 0.0
                    failures.append(failure(topic, exc.code, exc.metadata))
                    continue
                review_cost = cost(review.get("failure", review))
                spent += review_cost or 0.0
                if review["reason"] == "generation_spending_limit":
                    raise Stop("the next source check could pass --max-usd")
                if review["status"] != "checked":
                    # The draft's length still counts; its claims are left out of the mean
                    # (owner, 2026-11-02: one invalid review had stopped a whole paid run).
                    failures.append({"topic": topic, "code": f"review_{review['reason']}"})
            writer_cost = cost(metadata)
            rows.append(
                draft_row(
                    inputs,
                    minimum=LENGTH_TARGET_MINIMUMS[payload.length],
                    maximum=LENGTH_LIMITS[payload.length],
                    content=content,
                    warnings=completion.warnings,
                    sources=sources,
                    cited_ids=completion.source_ids,
                    review=review,
                    cost_usd=None
                    if writer_cost is None or review_cost is None
                    else writer_cost + review_cost,
                    seconds=time.monotonic() - started,
                )
            )
            print(f"measured {len(rows)}/{len(topics)}: {topic}", file=sys.stderr)
    except Stop as stop:
        report["stopped"] = str(stop)
    report["summary"] = summary(rows, failures)
    report["spent_usd"] = round(spent, 6)
    return report


def print_report(report: dict) -> None:
    print(f"Writer prompt: {report['prompt_version']}  cap: ${report['max_usd']:.2f}")
    if report["stopped"]:
        print(f"STOPPED EARLY: {report['stopped']}. Drafts measured so far are below.")
    for row in report["rows"]:
        print(
            f"- {row['length']:<6} {row['characters']:>5} chars ({row['words']} words), "
            f"target {row['target'][0]}–{row['target'][1]}: {row['status']}; "
            f"chunks {row['cited_chunks']}/{row['received_chunks']} cited, "
            f"documents {row['cited_documents']}/{row['received_documents']}; "
            f"unsupported {row['unsupported']}; ${row['cost_usd']}; {row['seconds']}s"
            f"\n  {row['topic']}"
        )
        for warning in row["warnings"]:
            print(f"  warning: {warning}")
    s = report["summary"]
    print(
        f"\n{s['drafts']} drafts: {s['in_range']} in range, {s['short_warned']} short with a "
        f"warning, {s['short_unwarned']} short without one. Median {s['median_characters']} "
        f"characters, median cited chunks {s['median_cited_chunks']}, mean unsupported claims "
        f"per checked draft {s['mean_unsupported_per_checked']}. Spent ${report['spent_usd']}."
    )
    for failure in s["failures"]:
        details = ", ".join(
            f"{key} {failure[key]}" for key in ("characters", "words", "usage") if key in failure
        )
        print(
            f"failed: {failure['code']} — {failure['topic']}" + (f" ({details})" if details else "")
        )
    print(
        "One draft per topic is a small, noisy sample: a small difference in unsupported "
        "claims is not conclusive."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-usd", type=float, required=True, help="Spending cap for the whole run (paid)"
    )
    parser.add_argument("--baseline-ref", help="Measure the writer prompt of this git revision")
    parser.add_argument("--out", type=Path, help="Also write the report as JSON here")
    parser.add_argument(
        "--topic", action="append", help="Only topics starting with this text (repeatable)"
    )
    parser.add_argument(
        "--writer-only", action="store_true", help="Skip the source check (length checks only)"
    )
    args = parser.parse_args(argv)
    if not 0 < args.max_usd <= 5:
        parser.error("--max-usd must be above 0 and at most 5")
    report = measure(args.max_usd, args.baseline_ref, args.topic, args.writer_only)
    print_report(report)
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report["stopped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
