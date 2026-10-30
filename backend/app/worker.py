import logging
from uuid import UUID

from celery import Celery
from celery.signals import after_setup_logger, task_failure
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app import storage
from app.chunking import chunk_text
from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import (
    EmbeddingError,
    TransientEmbeddingError,
    embed_texts,
    embedding_lock,
    profile_key,
)
from app.extraction import ExtractionError, extract_pdf, page_range
from app.logging import configure_worker_logging
from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument

celery_app = Celery("social_platform", broker=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_concurrency=2,
    task_soft_time_limit=90,
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 360},
    task_ignore_result=True,
)
after_setup_logger.connect(configure_worker_logging, weak=False)
celery_app.conf.beat_schedule = {
    "recover-durable-jobs": {"task": "social.reconcile_jobs", "schedule": 60.0},
}
logger = logging.getLogger(__name__)


@celery_app.task(
    name="social.foundation_probe",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def foundation_probe(job_id: str) -> None:
    """Database-backed, idempotent worker smoke test; no document contents in messages."""
    with SessionLocal.begin() as session:
        job = session.scalar(
            select(IngestionJob).where(IngestionJob.id == UUID(job_id)).with_for_update()
        )
        if job is None or job.status == "Ready":
            return
        if job.kind != "foundation_probe":
            raise ValueError("Unsupported job kind")
        job.attempts += 1
        job.status = "Ready"
        logger.info(
            "foundation_probe_complete",
            extra={
                "job_id": job_id,
                "document_id": str(job.document_id),
                "request_id": job.request_id,
            },
        )


@celery_app.task(
    name="social.process_text",
    autoretry_for=(OperationalError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def process_text(job_id: str) -> None:
    pages: list[tuple[int, int]] | None = None
    extracted: str | None = None
    failure: str | None = None
    with SessionLocal() as session:
        reference = session.get(IngestionJob, UUID(job_id))
        if reference is None or reference.kind != "text_ingestion":
            return
        document = session.get(KnowledgeDocument, reference.document_id)
        key = document.storage_key if document and document.source_type == "pdf" else None
    if key:
        # Parsing can take seconds, so no row lock is held; the locked step below checks
        # that the document still exists before writing anything.
        try:
            extracted, pages = extract_pdf(storage.read(key))
        except ExtractionError as exc:
            failure = exc.code
        except storage.StorageError as exc:
            failure = str(exc)
    with SessionLocal.begin() as session:
        reference = session.get(IngestionJob, UUID(job_id))
        if reference is None or reference.kind != "text_ingestion":
            return
        # Consistent document-before-job lock ordering serializes retry/delete/delivery.
        document = session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == reference.document_id)
            .with_for_update()
        )
        if document is None:
            return
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == UUID(job_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None or job.status == "Ready":
            return
        job.attempts += 1
        if failure is not None:
            # Actionable and not retried automatically: the same bytes fail the same way.
            document.status = job.status = "Failed"
            document.processing_stage = "failed"
            document.error_code = job.error_code = failure
            logger.info(
                "extraction_failed",
                extra={"job_id": job_id, "document_id": str(document.id), "error_code": failure},
            )
            return
        document.status = job.status = "Processing"
        if extracted is not None:
            document.source_text = extracted
        chunks = chunk_text(document.source_text or "")
        if pages:
            for values in chunks:
                location = values["source_location"]
                location.update(page_range(pages, location["char_start"], location["char_end"]))
        session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        for order, values in enumerate(chunks):
            session.add(
                KnowledgeChunk(
                    user_id=document.user_id,
                    workspace_id=document.workspace_id,
                    document_id=document.id,
                    chunk_order=order,
                    **values,
                )
            )
        document.processing_stage = "text_prepared"
        document.error_code = job.error_code = None
        # Ready is reserved for fully embedded documents. This job only prepares text.
        job.status = "Ready"
        logger.info(
            "text_prepared",
            extra={"job_id": job_id, "document_id": str(document.id), "request_id": job.request_id},
        )


@task_failure.connect
def record_ingestion_failure(sender=None, args=None, **kwargs):
    if getattr(sender, "name", None) != "social.process_text" or not args:
        return
    with SessionLocal.begin() as session:
        reference = session.get(IngestionJob, UUID(args[0]))
        if reference is None:
            return
        document = session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == reference.document_id)
            .with_for_update()
        )
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == reference.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if document is not None and job is not None and job.status != "Ready":
            document.status = job.status = "Failed"
            document.processing_stage = "failed"
            document.error_code = job.error_code = "processing_failed"
            job.attempts += 1


@celery_app.task(
    name="social.embed_document",
    autoretry_for=(OperationalError, TransientEmbeddingError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=4,
    soft_time_limit=240,
    time_limit=270,
)
def embed_document(job_id: str) -> None:
    with embedding_lock(job_id) as acquired:
        if not acquired:
            return
        settings = get_settings()
        profile = profile_key()
        with SessionLocal.begin() as session:
            job = session.get(IngestionJob, UUID(job_id))
            if job is None or job.kind != "embedding":
                return
            document = session.get(KnowledgeDocument, job.document_id)
            if document is None or document.embedding_profile != profile or job.status == "Ready":
                return
            job.attempts += 1
            job.status = document.status = "Processing"
            document.processing_stage = "embedding"
            document_id = document.id
        while True:
            with SessionLocal() as session:
                document = session.get(KnowledgeDocument, document_id)
                if document is None or document.embedding_profile != profile:
                    return
                chunks = list(
                    session.scalars(
                        select(KnowledgeChunk)
                        .where(
                            KnowledgeChunk.document_id == document_id,
                        )
                        .order_by(KnowledgeChunk.chunk_order)
                    )
                )
                if not chunks:
                    raise EmbeddingError("embedding_no_chunks")
                pending = [
                    c
                    for c in chunks
                    if c.embedding_profile != profile
                    or c.embedding is None
                    or c.embedding_dimensions != settings.embedding_dimensions
                    or c.embedding_model != settings.embedding_model
                ]
                batch = [(c.id, c.content) for c in pending[: settings.embedding_batch_size]]
            if not batch:
                break
            vectors = embed_texts([content for _, content in batch])
            # No DB transaction or row lock is held while contacting the provider.
            with SessionLocal.begin() as session:
                document = session.scalar(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.id == document_id)
                    .with_for_update()
                )
                if document is None or document.embedding_profile != profile:
                    return
                for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                    chunk = session.get(KnowledgeChunk, chunk_id)
                    if chunk is None:
                        return
                    chunk.embedding = vector
                    chunk.embedding_model = settings.embedding_model
                    chunk.embedding_dimensions = settings.embedding_dimensions
                    chunk.embedding_profile = profile
        with SessionLocal.begin() as session:
            document = session.scalar(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .with_for_update()
            )
            job = session.get(IngestionJob, UUID(job_id))
            if document is None or job is None or document.embedding_profile != profile:
                return
            document.status = job.status = "Ready"
            document.processing_stage = "ready"
            document.error_code = job.error_code = None
            logger.info(
                "embedding_complete",
                extra={
                    "job_id": job_id,
                    "document_id": str(document_id),
                    "request_id": job.request_id,
                },
            )


@task_failure.connect
def record_embedding_failure(sender=None, args=None, exception=None, **kwargs):
    if getattr(sender, "name", None) != "social.embed_document" or not args:
        return
    with SessionLocal.begin() as session:
        reference = session.get(IngestionJob, UUID(args[0]))
        if reference is None:
            return
        document = session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == reference.document_id)
            .with_for_update()
        )
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == reference.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            document is not None
            and job is not None
            and job.status != "Ready"
            and document.embedding_profile == profile_key()
        ):
            document.status = job.status = "Failed"
            document.processing_stage = "embedding_failed"
            document.error_code = job.error_code = (
                exception.code if isinstance(exception, EmbeddingError) else "embedding_failed"
            )


@celery_app.task(name="social.reconcile_jobs", ignore_result=True)
def reconcile_jobs() -> int:
    from app.reconcile import requeue_pending

    count = requeue_pending()
    logger.info("durable_jobs_reconciled", extra={"requeued_count": count})
    return count
