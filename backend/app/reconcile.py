"""Recover durable jobs; scheduled every minute and also runnable with python -m app.reconcile."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.embeddings import embedding_lock
from app.knowledge import dispatch, dispatch_embeddings
from app.models import IngestionJob, KnowledgeDocument

PENDING_AGE = timedelta(minutes=2)
PROCESSING_AGE = timedelta(minutes=10)  # Exceeds task hard limits and broker visibility timeout.


def requeue_pending() -> int:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        candidates = list(
            session.scalars(
                select(IngestionJob.id)
                .where(
                    IngestionJob.kind.in_(["text_ingestion", "embedding"]),
                    or_(
                        (IngestionJob.status == "Pending")
                        & (IngestionJob.updated_at < now - PENDING_AGE),
                        (IngestionJob.status == "Processing")
                        & (IngestionJob.updated_at < now - PROCESSING_AGE),
                    ),
                )
                .order_by(IngestionJob.created_at)
                .limit(100)
            )
        )
    count = 0
    for job_id in candidates:
        # An active embedding worker holds this advisory lock during provider calls.
        with embedding_lock(str(job_id)) as acquired:
            if not acquired:
                continue
            with SessionLocal.begin() as session:
                reference = session.get(IngestionJob, job_id)
                if reference is None:
                    continue
                document = session.scalar(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.id == reference.document_id)
                    .with_for_update()
                )
                job = session.scalar(
                    select(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if document is None or job is None:
                    continue
                age = PENDING_AGE if job.status == "Pending" else PROCESSING_AGE
                if job.status not in ("Pending", "Processing") or job.updated_at >= now - age:
                    continue
                job.status = "Pending"
                job.updated_at = now
                job.error_code = document.error_code = None
                document.status = "Processing" if job.kind == "embedding" else "Pending"
                document.processing_stage = (
                    "embedding_pending" if job.kind == "embedding" else "pending"
                )
                kind, document_id = job.kind, document.id
        # Release the advisory lock before dispatch, so a fast worker can acquire it.
        (dispatch_embeddings if kind == "embedding" else dispatch)(job_id, document_id)
        count += 1
    return count


if __name__ == "__main__":
    print(f"Requeued {requeue_pending()} durable jobs.")
