from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import String, delete, func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.brand import local_only
from app.db import SessionLocal
from app.grounding import REVIEW_VERSION, blocked_review, text_fingerprint
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import GenerationRun, Post

router = APIRouter(prefix="/posts", tags=["drafts"], dependencies=[Depends(local_only)])


class DraftValues(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    platform: Literal["linkedin", "facebook"] = "linkedin"
    language: Literal["en", "he"] = "en"
    content: str = Field(min_length=1, max_length=5000)
    status: Literal["Draft"] = "Draft"

    @model_validator(mode="after")
    def check_content(self):
        if "\x00" in self.content or (self.platform == "linkedin" and len(self.content) > 3000):
            raise ValueError("Invalid draft content")
        return self


class CreateDraft(DraftValues):
    save_key: UUID
    generation_run_id: UUID | None = None


class UpdateDraft(DraftValues):
    version: int = Field(ge=1)


def serialize(post):
    return {
        "id": str(post.id),
        "platform": post.platform,
        "language": post.language,
        "content": post.content,
        "status": post.status,
        "version": post.version,
        "generation_run_id": str(post.generation_run_id) if post.generation_run_id else None,
        "generation_settings": post.generation_settings,
        "sources": post.source_snapshots,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


def owned(post_id, session):
    post = session.scalar(
        select(Post).where(
            Post.id == post_id,
            Post.user_id == LOCAL_USER_ID,
            Post.workspace_id == LOCAL_WORKSPACE_ID,
        )
    )
    if post is None:
        raise HTTPException(404, "Draft not found.")
    return post


@router.post("", status_code=201)
def create_draft(payload: CreateDraft):
    values = payload.model_dump(exclude={"save_key", "generation_run_id"})
    with SessionLocal.begin() as session:
        seed_local_scope(session)
        sources, metadata = [], {}
        if payload.generation_run_id:
            run = session.scalar(
                select(GenerationRun).where(
                    GenerationRun.id == payload.generation_run_id,
                    GenerationRun.user_id == LOCAL_USER_ID,
                    GenerationRun.workspace_id == LOCAL_WORKSPACE_ID,
                )
            )
            if run is None or run.status != "Ready":
                raise HTTPException(404, "Generation not found.")
            if (
                run.result["platform"] != payload.platform
                or run.result["language"] != payload.language
            ):
                raise HTTPException(409, "draft_generation_mismatch")
            if (
                run.result.get("metadata", {}).get("grounding_review", {}).get("version")
                != REVIEW_VERSION
            ):
                raise HTTPException(409, "generation_review_required")
            sources = run.result["sources"]
            review = run.result["metadata"]["grounding_review"]
            metadata = {
                **run.result["metadata"],
                # The review applies to this draft only if it was saved unedited.
                "grounding_review": {
                    **review,
                    "checked_version": 1 if payload.content == run.result["content"] else None,
                },
                "warnings": run.result["warnings"],
                "grounded": run.result["grounded"] and payload.content == run.result["content"],
                "grounding_review_scope": "original_generation",
            }
        post_id = session.scalar(
            insert(Post)
            .values(
                **values,
                save_key=payload.save_key,
                generation_run_id=payload.generation_run_id,
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                source_snapshots=sources,
                generation_settings=metadata,
            )
            .on_conflict_do_nothing()
            .returning(Post.id)
        )
        if post_id is None:
            existing = session.scalar(
                select(Post).where(
                    Post.workspace_id == LOCAL_WORKSPACE_ID,
                    Post.user_id == LOCAL_USER_ID,
                    Post.save_key == payload.save_key,
                )
            )
            if (
                existing is None
                or any(getattr(existing, key) != value for key, value in values.items())
                or existing.generation_run_id != payload.generation_run_id
            ):
                raise HTTPException(409, "draft_save_conflict")
            return serialize(existing)
        return serialize(owned(post_id, session))


@router.get("")
def list_drafts(
    platform: Literal["linkedin", "facebook"] | None = None,
    status: Literal["Draft"] = "Draft",
    q: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    with SessionLocal() as session:
        query = select(Post).where(
            Post.user_id == LOCAL_USER_ID,
            Post.workspace_id == LOCAL_WORKSPACE_ID,
            Post.status == status,
        )
        if platform:
            query = query.where(Post.platform == platform)
        if q.strip():
            config = literal_column("'simple'::regconfig", type_=String())
            match = func.to_tsvector(config, Post.content).op("@@")(
                func.plainto_tsquery(config, q.strip())
            )
            query = query.where(
                or_(match, func.lower(Post.content).contains(q.strip().lower(), autoescape=True))
            )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        posts = session.scalars(
            query.order_by(Post.created_at.desc(), Post.id).offset(offset).limit(limit)
        )
        return {"items": [serialize(post) for post in posts], "total": total}


@router.get("/{post_id}")
def get_draft(post_id: UUID):
    with SessionLocal() as session:
        return serialize(owned(post_id, session))


@router.put("/{post_id}")
def update_draft(post_id: UUID, payload: UpdateDraft):
    with SessionLocal.begin() as session:
        post = owned(post_id, session)
        if post.generation_run_id and (
            post.platform != payload.platform or post.language != payload.language
        ):
            raise HTTPException(409, "draft_generation_mismatch")
        metadata = dict(post.generation_settings)
        if payload.content != post.content:
            metadata["grounded"] = False
        # Saving a blocked text again, under any version number, keeps it blocked.
        blocked_at = metadata.get("blocked_texts", {}).get(text_fingerprint(payload.content))
        if blocked_at:
            metadata["grounding_review"] = blocked_review(blocked_at, payload.version + 1)
            metadata["grounded"] = False
        updated = session.scalar(
            update(Post)
            .where(
                Post.id == post_id,
                Post.user_id == LOCAL_USER_ID,
                Post.workspace_id == LOCAL_WORKSPACE_ID,
                Post.version == payload.version,
            )
            .values(
                **payload.model_dump(exclude={"version"}),
                version=Post.version + 1,
                generation_settings=metadata,
            )
            .returning(Post)
        )
        if updated is None:
            raise HTTPException(409, "draft_edit_conflict")
        return serialize(updated)


@router.delete("/{post_id}")
def delete_draft(post_id: UUID):
    with SessionLocal.begin() as session:
        post = owned(post_id, session)
        run_id = post.generation_run_id
        session.execute(delete(Post).where(Post.id == post_id))
        if run_id:
            session.execute(
                delete(GenerationRun).where(
                    GenerationRun.id == run_id,
                    GenerationRun.user_id == LOCAL_USER_ID,
                    GenerationRun.workspace_id == LOCAL_WORKSPACE_ID,
                )
            )
    return {"deleted": True}
