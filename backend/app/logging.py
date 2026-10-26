import json
import logging
from datetime import UTC, datetime


class WorkerJSONFormatter(logging.Formatter):
    """Emit only declared metadata; never serialize arbitrary extra fields or exception bodies."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "job_id": getattr(record, "job_id", None),
            "document_id": getattr(record, "document_id", None),
            "request_id": getattr(record, "request_id", None),
        }
        if hasattr(record, "requeued_count"):
            payload["requeued_count"] = record.requeued_count
        if record.exc_info and record.exc_info[0]:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


def configure_worker_logging(logger=None, **kwargs):
    target = logger or logging.getLogger()
    for handler in target.handlers:
        handler.setFormatter(WorkerJSONFormatter())
