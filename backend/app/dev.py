from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.db import SessionLocal
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import IngestionJob
from app.worker import foundation_probe

router = APIRouter(prefix="/dev", tags=["local development"])


@router.post("/jobs/probe", status_code=202)
def enqueue_probe(request: Request):
    with SessionLocal.begin() as session:
        seed_local_scope(session)
        job = IngestionJob(
            user_id=LOCAL_USER_ID,
            workspace_id=LOCAL_WORKSPACE_ID,
            request_id=request.state.request_id,
            kind="foundation_probe",
        )
        session.add(job)
        session.flush()
        job_id = str(job.id)
    try:
        foundation_probe.delay(job_id)
    except Exception:
        with SessionLocal.begin() as session:
            stored = session.get(IngestionJob, UUID(job_id))
            if stored is not None:
                stored.status = "Failed"
                stored.error_code = "dispatch_failed"
        raise HTTPException(503, "Job dispatch failed.") from None
    return {"id": job_id, "status": "Pending"}


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID):
    with SessionLocal() as session:
        job = session.get(IngestionJob, job_id)
        if job is None or job.user_id != LOCAL_USER_ID or job.workspace_id != LOCAL_WORKSPACE_ID:
            raise HTTPException(404, "Job not found.")
        return {"id": str(job.id), "status": job.status, "attempts": job.attempts}
