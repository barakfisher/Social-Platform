import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.brand import local_only
from app.chunking import normalize_text
from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import EmbeddingError, configured, embed_texts, profile_key
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.retrieval import search_context
from app.worker import process_text

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(local_only)])


class TextSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=100000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Title cannot contain null bytes")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = normalize_text(value)
        if not value or "\x00" in value:
            raise ValueError("Text must be nonempty and contain no null bytes")
        return value


def owned(document_id: UUID, session, lock=False):
    query = select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.user_id == LOCAL_USER_ID,
        KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID,
    )
    document = session.scalar(query.with_for_update() if lock else query)
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


def summary(document, session):
    return {
        "id": str(document.id),
        "title": document.title,
        "status": (
            "Processing"
            if document.status == "Ready" and document.embedding_profile != profile_key()
            else document.status
        ),
        "stage": (
            "text_prepared"
            if document.status == "Ready" and document.embedding_profile != profile_key()
            else document.processing_stage
        ),
        "embedded_chunk_count": session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.embedding_profile == profile_key(),
                KnowledgeChunk.embedding.is_not(None),
            )
        ),
        "error_code": document.error_code,
        "chunk_count": session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document.id)
        ),
        "created_at": document.created_at.isoformat(),
        "status_url": f"/knowledge/{document.id}",
    }


def dispatch(job_id: UUID, document_id: UUID):
    try:
        process_text.apply_async(args=[str(job_id)], task_id=str(job_id))
    except Exception:
        # The durable records survive a broker outage and can be retried by the user.
        with SessionLocal.begin() as session:
            document = session.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .with_for_update()
            )
            job = session.get(IngestionJob, job_id)
            if document is not None and job is not None and job.status == "Pending":
                document.status = job.status = "Failed"
                document.processing_stage = "failed"
                document.error_code = job.error_code = "dispatch_failed"


@router.post("/text", status_code=202)
def submit_text(payload: TextSubmission, request: Request):
    checksum = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
    with SessionLocal.begin() as session:
        seed_local_scope(session)
        document_id = session.scalar(
            insert(KnowledgeDocument)
            .values(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                title=payload.title,
                source_type="text",
                source_text=payload.text,
                checksum=checksum,
                status="Pending",
            )
            .on_conflict_do_nothing()
            .returning(KnowledgeDocument.id)
        )
        if document_id is None:
            document = session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID,
                    KnowledgeDocument.user_id == LOCAL_USER_ID,
                    KnowledgeDocument.source_type == "text",
                    KnowledgeDocument.checksum == checksum,
                )
            )
            return {**summary(document, session), "duplicate": True}
        job = IngestionJob(
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            document_id=document_id,
            request_id=request.state.request_id,
            kind="text_ingestion",
        )
        session.add(job)
        session.flush()
        job_id = job.id
    dispatch(job_id, document_id)
    with SessionLocal() as session:
        return {**summary(owned(document_id, session), session), "duplicate": False}


@router.get("")
def list_documents(
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 20
):
    with SessionLocal() as session:
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.user_id == LOCAL_USER_ID,
            KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID,
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        documents = session.scalars(
            query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id)
            .offset(offset)
            .limit(limit)
        )
        return {"items": [summary(d, session) for d in documents], "total": total}


@router.get("/configuration")
def embedding_configuration():
    settings = get_settings()
    return {
        "configured": configured(),
        "model": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
    }


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/search")
def search_knowledge(payload: KnowledgeQuery):
    from app.chunking import token_count

    if token_count(payload.query) > 2000:
        raise HTTPException(422, "Search query is too long.")
    try:
        vector = embed_texts([payload.query])[0]
    except EmbeddingError as exc:
        raise HTTPException(503, exc.code) from None
    with SessionLocal() as session:
        return {
            "items": search_context(
                session,
                vector,
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                limit=payload.limit,
            )
        }


@router.get("/{document_id}")
def get_document(document_id: UUID):
    with SessionLocal() as session:
        document = owned(document_id, session)
        return {**summary(document, session), "text": document.source_text}


@router.post("/{document_id}/retry", status_code=202)
def retry_document(document_id: UUID):
    with SessionLocal.begin() as session:
        document = owned(document_id, session, lock=True)
        if (
            document.processing_stage == "text_prepared"
            or document.status == "Ready"
            or session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document_id)
            )
        ):
            raise HTTPException(409, "Text is already prepared.")
        job = session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.kind == "text_ingestion",
            )
            .with_for_update()
        )
        if job is None:
            raise HTTPException(409, "This source cannot be retried as pasted text.")
        document.status = job.status = "Pending"
        document.processing_stage = "pending"
        document.error_code = job.error_code = None
        job_id = job.id
    dispatch(job_id, document_id)
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)


@router.delete("/{document_id}")
def delete_document(document_id: UUID):
    with SessionLocal.begin() as session:
        owned(document_id, session, lock=True)
        session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    return {"deleted": True}


@router.post("/{document_id}/embed", status_code=202)
def start_embeddings(document_id: UUID, request: Request):
    if not configured():
        raise HTTPException(503, "embedding_not_configured")
    profile = profile_key()
    with SessionLocal.begin() as session:
        document = owned(document_id, session, lock=True)
        count = session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
        )
        if not count:
            raise HTTPException(409, "Prepare text before creating embeddings.")
        if document.status == "Ready" and document.embedding_profile == profile:
            return summary(document, session)
        job = session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.kind == "embedding",
            )
            .with_for_update()
        )
        if job is None:
            job = IngestionJob(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                document_id=document_id,
                kind="embedding",
                request_id=request.state.request_id,
            )
            session.add(job)
        job.status = "Pending"
        job.error_code = document.error_code = None
        document.status = "Processing"
        document.processing_stage = "embedding_pending"
        document.embedding_profile = profile
        session.flush()
        job_id = job.id
    dispatch_embeddings(job_id, document_id)
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)


def dispatch_embeddings(job_id: UUID, document_id: UUID):
    from app.worker import embed_document

    try:
        embed_document.apply_async(args=[str(job_id)], task_id=str(job_id))
    except Exception:
        with SessionLocal.begin() as session:
            document = session.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .with_for_update()
            )
            job = session.get(IngestionJob, job_id)
            if document is not None and job is not None and job.status == "Pending":
                document.status = job.status = "Failed"
                document.processing_stage = "embedding_failed"
                document.error_code = job.error_code = "dispatch_failed"
