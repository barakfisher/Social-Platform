import json
import logging
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from test_knowledge import job_for

from app.logging import WorkerJSONFormatter
from app.models import IngestionJob
from app.reconcile import requeue_pending
from app.worker import celery_app, reconcile_jobs


def test_worker_log_metadata_is_structured_and_extra_contents_are_excluded():
    record = logging.LogRecord("worker", logging.INFO, __file__, 1, "text_prepared", (), None)
    record.job_id = "job-id"
    record.document_id = "document-id"
    record.request_id = "request-id"
    record.source_text = "private document body"
    record.api_key = "private credential"
    result = WorkerJSONFormatter().format(record)
    assert json.loads(result)["job_id"] == "job-id"
    assert json.loads(result)["document_id"] == "document-id"
    assert json.loads(result)["request_id"] == "request-id"
    assert "private document body" not in result
    assert "private credential" not in result


def test_expired_processing_job_recovers_but_recent_job_is_not_requeued(api):
    client, factory, dispatch = api
    stale = client.post("/knowledge/text", json={"title": "Stale", "text": "stale source"}).json()
    recent = client.post(
        "/knowledge/text", json={"title": "Recent", "text": "recent source"}
    ).json()
    stale_id, recent_id = job_for(factory, stale["id"]), job_for(factory, recent["id"])
    with factory.begin() as session:
        for job_id, minutes in [(stale_id, 11), (recent_id, 1)]:
            job = session.get(IngestionJob, UUID(job_id))
            job.status = "Processing"
            job.updated_at = datetime.now(UTC) - timedelta(minutes=minutes)
    dispatch.reset_mock()
    with (
        patch("app.reconcile.SessionLocal", factory),
        patch("app.reconcile.embedding_lock", return_value=nullcontext(True)),
    ):
        assert requeue_pending() == 1
    dispatch.assert_called_once_with(args=[stale_id], task_id=stale_id)
    with factory() as session:
        assert session.get(IngestionJob, UUID(stale_id)).status == "Pending"
        assert session.get(IngestionJob, UUID(recent_id)).status == "Processing"


def test_locked_active_worker_is_not_recovered(api):
    client, factory, dispatch = api
    item = client.post("/knowledge/text", json={"title": "Active", "text": "active source"}).json()
    job_id = job_for(factory, item["id"])
    with factory.begin() as session:
        session.get(IngestionJob, UUID(job_id)).updated_at = datetime.now(UTC) - timedelta(
            minutes=11
        )
    dispatch.reset_mock()
    with (
        patch("app.reconcile.SessionLocal", factory),
        patch("app.reconcile.embedding_lock", return_value=nullcontext(False)),
    ):
        assert requeue_pending() == 0
    dispatch.assert_not_called()


def test_reconciliation_is_scheduled_and_dispatches_through_worker():
    assert celery_app.conf.beat_schedule["recover-durable-jobs"] == {
        "task": "social.reconcile_jobs",
        "schedule": 60.0,
    }
    with patch("app.reconcile.requeue_pending", return_value=2):
        assert reconcile_jobs() == 2
