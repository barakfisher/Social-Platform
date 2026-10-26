"""Exercise broker crashes and automatic recovery in an isolated, disposable Compose project."""

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "social-verify-" + uuid4().hex[:8]
COMMAND = ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "verification/compose.yml")]


def compose(*arguments, check=True):
    result = subprocess.run(
        [*COMMAND, *arguments], cwd=ROOT, text=True, capture_output=True, timeout=300
    )
    if check and result.returncode:
        raise RuntimeError(f"Verification command failed: {arguments}\n{result.stderr[-3000:]}")
    return result.stdout.strip()


def api(base, path, data=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def wait_for_prepared(base, document_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = api(base, "/knowledge/" + document_id)
        if result["stage"] == "text_prepared":
            assert result["chunk_count"] == 1, result
            return result
        if result["status"] == "Failed":
            raise AssertionError(result)
        time.sleep(1)
    raise TimeoutError("Isolated job did not reach text_prepared")


def inspect_job(document_id):
    code = f"""
import json
from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.models import IngestionJob
with SessionLocal() as session:
 job=session.scalar(select(IngestionJob).where(IngestionJob.document_id==UUID({document_id!r})))
 print(json.dumps({{"id":str(job.id),"status":job.status,"attempts":job.attempts}}))
"""
    return json.loads(compose("exec", "-T", "api", "python", "-c", code))


def verify():
    print("Starting disposable services: " + PROJECT, flush=True)
    try:
        compose("up", "-d", "--build", "--wait", "api")
        port = compose("port", "api", "8000").split(":")[-1]
        base = "http://127.0.0.1:" + port
        first = api(
            base,
            "/knowledge/text",
            {
                "title": "Broker crash check",
                "text": "Private verification marker: broker persistence. בדיקת תור.",
            },
        )
        assert first["status"] == "Pending"
        job = inspect_job(first["id"])
        assert int(compose("exec", "-T", "redis", "redis-cli", "LLEN", "celery")) >= 1
        # Allow the configured every-second AOF flush before abrupt process termination.
        time.sleep(2)
        compose("kill", "-s", "SIGKILL", "redis")
        compose("up", "-d", "--wait", "redis")
        assert int(compose("exec", "-T", "redis", "redis-cli", "LLEN", "celery")) >= 1
        print("PASS: queued job survived a SIGKILL and Redis AOF restart.", flush=True)
        compose("up", "-d", "worker")
        wait_for_prepared(base, first["id"])
        assert inspect_job(first["id"])["attempts"] == 1
        # Send the same delivery again; final chunks and attempt count must remain unchanged.
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            f"from app.worker import process_text; process_text.apply_async(args=[{job['id']!r}])",
        )
        time.sleep(2)
        assert inspect_job(first["id"])["attempts"] == 1
        assert api(base, "/knowledge/" + first["id"])["chunk_count"] == 1
        print(
            "PASS: worker consumed recovered job; duplicate delivery stayed idempotent.",
            flush=True,
        )
        compose("stop", "-t", "15", "worker")
        # Lose a second accepted enqueue while keeping its durable database records.
        second = api(
            base,
            "/knowledge/text",
            {"title": "Lost enqueue check", "text": "Durable source recovery."},
        )
        compose("exec", "-T", "redis", "redis-cli", "FLUSHDB")
        assert api(base, "/knowledge/" + first["id"])["stage"] == "text_prepared"
        assert inspect_job(first["id"])["status"] == "Ready"
        code = f"""
from datetime import UTC,datetime,timedelta
from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.models import IngestionJob
with SessionLocal.begin() as session:
 job=session.scalar(select(IngestionJob).where(IngestionJob.document_id==UUID({second["id"]!r})))
 job.updated_at=datetime.now(UTC)-timedelta(minutes=3)
"""
        compose("exec", "-T", "api", "python", "-c", code)
        compose("up", "-d", "worker", "scheduler")
        print("Waiting for the real 60-second scheduler to recover the lost enqueue…", flush=True)
        wait_for_prepared(base, second["id"], timeout=100)
        logs = compose("logs", "--no-color", "--no-log-prefix", "worker")
        records = []
        for line in logs.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        prepared = [entry for entry in records if entry.get("event") == "text_prepared"]
        assert prepared and all(
            entry.get("job_id") and entry.get("document_id") and entry.get("request_id")
            for entry in prepared
        )
        assert "Private verification marker" not in logs
        assert "Durable source recovery." not in logs
        compose("stop", "-t", "15", "worker")
        assert api(base, "/knowledge/" + second["id"])["stage"] == "text_prepared"
        print(
            "PASS: durable status survived Redis loss; scheduled recovery restored the enqueue.",
            flush=True,
        )
        print(
            "PASS: correlated logs exclude source text; graceful stop preserved results.",
            flush=True,
        )
        print(
            "Worker recovery verification passed. No development services or data were changed.",
            flush=True,
        )
    finally:
        compose("down", "-v", "--remove-orphans", check=False)


if __name__ == "__main__":
    verify()
