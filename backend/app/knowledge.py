import hashlib
import unicodedata
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app import storage
from app.brand import local_only
from app.chunking import chunk_text, normalize_text
from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import EmbeddingError, configured, embed_texts, profile_key
from app.extraction import CONTROL_CHARACTERS, ExtractionError, decode_text_file
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.refresh import (
    ACTIVE,
    AWAITING,
    append_heading,
    apply,
    changes,
    keep,
    preview,
    staging_for,
    today,
)
from app.retrieval import search_context
from app.web_fetch import FetchError, fallback_title, normalize_url
from app.worker import process_text

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(local_only)])
# Knowledge is drawn on for facts; sample posts are the owner's finished posts.
DocumentKind = Literal["knowledge", "sample_posts"]


class TextSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=100000)
    kind: DocumentKind = "knowledge"

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
        # Staging copies of a page being loaded again are internal (app/refresh.py).
        KnowledgeDocument.replaces_id.is_(None),
    )
    document = session.scalar(query.with_for_update() if lock else query)
    if document is None:
        raise HTTPException(404, "Document not found.")
    return document


def summary(document, session):
    return {
        "id": str(document.id),
        "title": document.title,
        "kind": document.kind,
        "source_type": document.source_type,
        "filename": document.source_reference if document.source_type in ("pdf", "txt") else None,
        "url": document.source_reference if document.source_type == "url" else None,
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
        "fetched_at": document.fetched_at.isoformat() if document.fetched_at else None,
        "refresh_result": document.refresh_result,
        "refresh": refresh_state(document, session),
        "status_url": f"/knowledge/{document.id}",
    }


def refresh_state(document, session):
    """The page being loaded again, if any; the original stays in use meanwhile."""
    if document.source_type != "url":
        return None
    staging = staging_for(session, document.id)
    if staging is None:
        return None
    state = {
        "status": staging.status,
        "stage": staging.processing_stage,
        "error_code": staging.error_code,
        "action": staging.refresh_action,
    }
    if staging.processing_stage == AWAITING:
        found = preview(document.source_text, staging.source_text)
        state.update(added_count=found["added_count"], removed_count=found["removed_count"])
    return state


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
                kind=payload.kind,
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


# Upload type comes from the extension and must match the file's own signature.
FILE_TYPES = {".pdf": "pdf", ".txt": "txt", ".md": "txt"}


def clean_filename(value: str) -> str:
    # Keep only the last path segment; the name is shown back, never used as a path.
    name = PurePosixPath(value.replace("\\", "/")).name
    name = unicodedata.normalize("NFC", CONTROL_CHARACTERS.sub("", name)).strip()
    if name in ("", ".", "..") or len(name) > 255:
        raise HTTPException(422, "file_name_invalid")
    return name


async def read_limited(request: Request) -> bytes:
    limit = get_settings().upload_max_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "file_too_large")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > limit:
            raise HTTPException(413, "file_too_large")
    return bytes(body)


@router.post("/files", status_code=202)
async def submit_file(
    request: Request,
    filename: Annotated[str, Query(min_length=1, max_length=1000)],
    title: Annotated[str | None, Query(max_length=300)] = None,
    kind: DocumentKind = "knowledge",
):
    """Raw file bytes as application/octet-stream (a type that needs a CORS preflight)."""
    name = clean_filename(filename)
    source_type = FILE_TYPES.get(PurePosixPath(name.lower()).suffix)
    if source_type is None:
        raise HTTPException(415, "file_type_unsupported")
    data = await read_limited(request)
    if not data:
        raise HTTPException(422, "source_empty")
    text = None
    if source_type == "pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(422, "file_signature_mismatch")
    else:
        try:
            text = decode_text_file(data)
        except ExtractionError as exc:
            raise HTTPException(422, exc.code) from None
    clean_title = normalize_text(title or "") or PurePosixPath(name).stem or name
    if "\x00" in clean_title:
        raise HTTPException(422, "validation_error")
    return await run_in_threadpool(
        store_file, request, data, name, clean_title[:300], source_type, text, kind
    )


def existing_file(session, source_type: str, checksum: str):
    return session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID,
            KnowledgeDocument.user_id == LOCAL_USER_ID,
            KnowledgeDocument.source_type == source_type,
            KnowledgeDocument.checksum == checksum,
        )
    )


def store_file(request, data, name, title, source_type, text, kind):
    # Duplicate policy: the same bytes and type in one workspace return the first document.
    checksum = hashlib.sha256(data).hexdigest()
    with SessionLocal() as session:
        document = existing_file(session, source_type, checksum)
        if document is not None:
            return {**summary(document, session), "duplicate": True}
    try:
        key = storage.put(data)
    except storage.StorageError as exc:
        raise HTTPException(503, str(exc)) from None
    try:
        with SessionLocal.begin() as session:
            seed_local_scope(session)
            document_id = session.scalar(
                insert(KnowledgeDocument)
                .values(
                    user_id=LOCAL_USER_ID,
                    workspace_id=LOCAL_WORKSPACE_ID,
                    title=title,
                    source_type=source_type,
                    source_reference=name,
                    source_text=text,
                    kind=kind,
                    storage_key=key,
                    checksum=checksum,
                    status="Pending",
                )
                .on_conflict_do_nothing()
                .returning(KnowledgeDocument.id)
            )
            if document_id is None:
                document = existing_file(session, source_type, checksum)
                storage.remove(key)
                if document is None:  # The original was deleted in between.
                    raise HTTPException(409, "upload_conflict")
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
    except Exception:
        # Nothing references the stored file unless the transaction committed.
        storage.remove(key)
        raise
    dispatch(job_id, document_id)
    with SessionLocal() as session:
        return {**summary(owned(document_id, session), session), "duplicate": False}


class UrlSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=300)
    kind: DocumentKind = "knowledge"


@router.post("/url", status_code=202)
def submit_url(payload: UrlSubmission, request: Request):
    """Checks the URL's form now; the worker resolves, checks and fetches it (app/web_fetch.py)."""
    try:
        url = normalize_url(payload.url)
    except FetchError as exc:
        raise HTTPException(422, exc.code) from None
    title = CONTROL_CHARACTERS.sub(" ", normalize_text(payload.title)).strip()
    # Duplicate policy: one source per normalized URL (fragment dropped) per workspace.
    checksum = hashlib.sha256(url.encode("utf-8")).hexdigest()
    with SessionLocal.begin() as session:
        seed_local_scope(session)
        document_id = session.scalar(
            insert(KnowledgeDocument)
            .values(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                title=title or fallback_title(url),
                source_type="url",
                source_reference=url,
                kind=payload.kind,
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
                    KnowledgeDocument.source_type == "url",
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
            KnowledgeDocument.replaces_id.is_(None),
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
        # Shown next to the upload control so the client checks the same limits.
        "upload_max_bytes": settings.upload_max_bytes,
        "pdf_max_pages": settings.pdf_max_pages,
        "file_types": sorted(FILE_TYPES),
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


class KindChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: DocumentKind


@router.patch("/{document_id}")
def change_kind(document_id: UUID, payload: KindChange):
    """Free and immediate at any stage: the kind is read when ideas are suggested, never
    when text is prepared or embedded, so nothing is processed again."""
    with SessionLocal.begin() as session:
        owned(document_id, session, lock=True)
        # updated_at stays: topic ideas sample the most recently updated documents, and a
        # kind is not new content.
        session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(kind=payload.kind, updated_at=KnowledgeDocument.updated_at)
        )
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)


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
        # "Process again" fetches a web page afresh; the old copy goes after commit.
        stale_page = document.storage_key if document.source_type == "url" else None
        if stale_page:
            document.storage_key = None
        job_id = job.id
    if stale_page:
        storage.remove(stale_page)
    dispatch(job_id, document_id)
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)


@router.delete("/{document_id}")
def delete_document(document_id: UUID):
    with SessionLocal.begin() as session:
        keys = [owned(document_id, session, lock=True).storage_key]
        staging = staging_for(session, document_id, lock=True)
        if staging is not None:
            keys.append(staging.storage_key)
        # The staging copy, chunks and jobs go with it (ON DELETE CASCADE).
        session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
    # After commit: a failure here leaves an unreferenced private file, never a dangling row.
    for key in keys:
        if key:
            storage.remove(key)
    return {"deleted": True}


@router.post("/{document_id}/refresh", status_code=202)
def refresh_page(document_id: UUID, request: Request):
    """Loads a web page again. The current version stays in use until the new one is ready;
    unchanged text costs nothing more (app/refresh.py)."""
    stale_key = None
    with SessionLocal.begin() as session:
        document = owned(document_id, session, lock=True)
        if document.source_type != "url":
            raise HTTPException(409, "refresh_not_supported")
        if document.processing_stage not in ("text_prepared", "ready"):
            raise HTTPException(409, "refresh_not_ready")
        staging = staging_for(session, document_id, lock=True)
        if staging is not None and staging.status in ACTIVE:
            # Already loading, or changes are waiting for the owner's choice.
            return summary(document, session)
        if staging is not None:
            # The last attempt failed; it is replaced by this one.
            stale_key = staging.storage_key
            session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
        url = document.source_reference or ""
        staging = KnowledgeDocument(
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            title=fallback_title(url),
            source_type="url",
            source_reference=url,
            replaces_id=document.id,
            status="Pending",
        )
        session.add(staging)
        session.flush()
        job = IngestionJob(
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            document_id=staging.id,
            request_id=request.state.request_id,
            kind="text_ingestion",
        )
        session.add(job)
        document.refresh_result = None
        session.flush()
        job_id, staging_id = job.id, staging.id
    if stale_key:
        storage.remove(stale_key)
    dispatch(job_id, staging_id)
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)


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
        staging = staging_for(session, document_id)
        if (
            staging is not None
            and staging.status in ACTIVE
            and staging.processing_stage != AWAITING
        ):
            raise HTTPException(409, "refresh_in_progress")
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


def awaiting(document_id: UUID, session):
    """The original (locked first) and its staging copy waiting for the owner's choice."""
    document = owned(document_id, session, lock=True)
    staging = staging_for(session, document_id, lock=True)
    if staging is None or staging.processing_stage != AWAITING:
        raise HTTPException(409, "refresh_not_awaiting")
    return document, staging


@router.get("/{document_id}/refresh-changes")
def refresh_changes(document_id: UUID):
    """Paragraphs the site added and removed since the version in use (first 30 of each)."""
    with SessionLocal.begin() as session:
        document, staging = awaiting(document_id, session)
        return preview(document.source_text, staging.source_text)


class RefreshDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["replace", "append", "keep"]


@router.post("/{document_id}/refresh-decision", status_code=202)
def decide_refresh(document_id: UUID, payload: RefreshDecision, request: Request):
    """Applies the owner's choice. A searchable source keeps its current version until the
    new chunks are embedded; one that is not searchable yet changes at once."""
    remove_key = None
    embed_job = None
    with SessionLocal.begin() as session:
        document, staging = awaiting(document_id, session)
        added, _ = changes(document.source_text, staging.source_text)
        if payload.action == "keep" or (payload.action == "append" and not added):
            remove_key = keep(session, document, staging)
        else:
            if document.status == "Ready" and not configured():
                raise HTTPException(503, "embedding_not_configured")
            if payload.action == "append":
                # Only paragraphs the source does not have yet, under a dated heading.
                staging.source_text = "\n\n".join([append_heading(today()), *added])
            staging.refresh_action = payload.action
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == staging.id))
            for order, values in enumerate(chunk_text(staging.source_text or "", added_on=today())):
                session.add(
                    KnowledgeChunk(
                        user_id=LOCAL_USER_ID,
                        workspace_id=LOCAL_WORKSPACE_ID,
                        document_id=staging.id,
                        chunk_order=order,
                        **values,
                    )
                )
            staging.processing_stage = "text_prepared"
            session.flush()
            if document.status == "Ready":
                job = IngestionJob(
                    user_id=LOCAL_USER_ID,
                    workspace_id=LOCAL_WORKSPACE_ID,
                    document_id=staging.id,
                    kind="embedding",
                    request_id=request.state.request_id,
                )
                session.add(job)
                staging.processing_stage = "embedding_pending"
                staging.embedding_profile = profile_key()
                session.flush()
                embed_job = (job.id, staging.id)
            else:
                remove_key = apply(session, document, staging)
    if remove_key:
        storage.remove(remove_key)
    if embed_job:
        dispatch_embeddings(*embed_job)
    with SessionLocal() as session:
        return summary(owned(document_id, session), session)
