""" "Check again": re-run the source check on the server-saved version of a draft.

The client never supplies the text to check. A generation result or a saved draft is
re-read from the database, so a review can only be attached to the version it checked.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update

from app.brand import local_only
from app.config import get_settings
from app.db import SessionLocal
from app.generation import GenerateInput, brand_constraints, generation_lock
from app.generation_provider import GenerationError
from app.grounding import blocked_review, check_draft, text_fingerprint
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID
from app.models import BrandDNA, GenerationRun, Post
from app.posts import serialize

router = APIRouter(tags=["review"], dependencies=[Depends(local_only)])


class RecheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Omitted means the model the draft was generated with.
    review_model: str | None = Field(default=None, max_length=200)


class RecheckDraftInput(RecheckInput):
    # The draft version the user is looking at; a newer saved version is a conflict.
    version: int = Field(ge=1)


def generation_inputs(inputs: dict, request_key: UUID) -> GenerateInput:
    try:
        return GenerateInput.model_validate({**inputs, "request_key": request_key})
    except ValidationError:
        # Inputs stored before tone/CTA presets cannot be rebuilt into writer preferences.
        raise HTTPException(409, "review_unavailable") from None


def review_model(requested: str | None, inputs: dict) -> str:
    settings = get_settings()
    model = requested or inputs.get("review_model") or settings.generation_review_model
    if model not in settings.generation_review_models:
        raise HTTPException(422, "review_model_unavailable")
    return model


def brand_values() -> dict:
    with SessionLocal() as session:
        brand = session.scalar(
            select(BrandDNA).where(
                BrandDNA.user_id == LOCAL_USER_ID, BrandDNA.workspace_id == LOCAL_WORKSPACE_ID
            )
        )
        if brand is None:
            raise HTTPException(409, "brand_setup_required")
        return brand_constraints(brand)


def run_check(content: str, sources: list[dict], inputs: GenerateInput, model: str) -> dict:
    try:
        return check_draft(
            content,
            sources,
            brand_values(),
            inputs.writer_preferences(),
            offer_details=inputs.offer_details,
            model_id=model,
        )
    except GenerationError as exc:
        raise HTTPException(409, exc.code) from None


@router.post("/generation/{run_id}/review")
def recheck_generation(run_id: UUID, payload: RecheckInput):
    with generation_lock(run_id) as acquired:
        if not acquired:
            raise HTTPException(409, "review_in_progress")
        with SessionLocal() as session:
            run = session.scalar(
                select(GenerationRun).where(
                    GenerationRun.id == run_id,
                    GenerationRun.user_id == LOCAL_USER_ID,
                    GenerationRun.workspace_id == LOCAL_WORKSPACE_ID,
                    GenerationRun.status == "Ready",
                )
            )
            if run is None:
                raise HTTPException(404, "Generation not found.")
            result, inputs = run.result, generation_inputs(run.inputs, run.request_key)
            model = review_model(payload.review_model, run.inputs)
        try:
            review = run_check(result["content"], result["sources"], inputs, model)
        except HTTPException as exc:
            if exc.detail != "draft_blocked":
                raise
            # Same outcome as a block on the first review: the run keeps no content, so it
            # can no longer be returned or saved, and no later check can replace the block.
            with SessionLocal.begin() as session:
                run = session.get(GenerationRun, run_id)
                if run is not None:
                    run.status = "Failed"
                    run.error_code = "draft_blocked"
                    run.result = {"metadata": run.result.get("metadata", {})}
            raise
        with SessionLocal.begin() as session:
            run = session.get(GenerationRun, run_id)
            if run is None:
                raise HTTPException(404, "Generation not found.")
            run.result = {
                **run.result,
                "grounded": review["status"] == "checked" and not review["findings"],
                "metadata": {**run.result["metadata"], "grounding_review": review},
            }
            return run.result


@router.post("/posts/{post_id}/review")
def recheck_draft(post_id: UUID, payload: RecheckDraftInput):
    with generation_lock(post_id) as acquired:
        if not acquired:
            raise HTTPException(409, "review_in_progress")
        with SessionLocal() as session:
            post = session.scalar(
                select(Post).where(
                    Post.id == post_id,
                    Post.user_id == LOCAL_USER_ID,
                    Post.workspace_id == LOCAL_WORKSPACE_ID,
                )
            )
            if post is None:
                raise HTTPException(404, "Draft not found.")
            if post.version != payload.version:
                raise HTTPException(409, "draft_edit_conflict")
            settings = post.generation_settings
            # Only generated drafts carry the sources and preferences a review needs.
            if "preferences" not in settings:
                raise HTTPException(409, "review_unavailable")
            # A block stands for its text, not its version number: re-saving or pasting back
            # the same words could otherwise replace it with a luckier review.
            if text_fingerprint(post.content) in settings.get("blocked_texts", {}):
                raise HTTPException(409, "draft_blocked")
            inputs = generation_inputs(settings["preferences"], post.id)
            model = review_model(payload.review_model, settings["preferences"])
            content, sources = post.content, post.source_snapshots
        try:
            review = run_check(content, sources, inputs, model)
        except HTTPException as exc:
            if exc.detail != "draft_blocked":
                raise
            # The owner's saved text is kept, never deleted, but recorded as blocked.
            review = blocked_review(datetime.now(UTC).isoformat(), payload.version)
        review["checked_version"] = payload.version
        with SessionLocal.begin() as session:
            post = session.get(Post, post_id)
            if post is None:
                raise HTTPException(404, "Draft not found.")
            blocked_texts = dict(post.generation_settings.get("blocked_texts", {}))
            if review["status"] == "blocked":
                blocked_texts[text_fingerprint(content)] = review["checked_at"]
            updated = session.scalar(
                update(Post)
                .where(
                    Post.id == post_id,
                    Post.user_id == LOCAL_USER_ID,
                    Post.workspace_id == LOCAL_WORKSPACE_ID,
                    Post.version == payload.version,
                )
                .values(
                    generation_settings={
                        **post.generation_settings,
                        "grounding_review": review,
                        "grounded": review["status"] == "checked" and not review["findings"],
                        "blocked_texts": blocked_texts,
                    }
                )
                .returning(Post)
            )
            if updated is None:
                raise HTTPException(409, "draft_edit_conflict")
            return serialize(updated)
