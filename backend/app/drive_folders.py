"""Connect, refresh and disconnect shared Google Drive folders (SP-30).

The owner shares a folder with the service account as Viewer, then connects it here. The
folder is checked once in the request, so a folder that is not shared fails at once; its
files are synced by the worker (app/drive_sync.py).
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app import drive, storage
from app.brand import local_only
from app.db import SessionLocal
from app.drive import DriveError
from app.drive_sync import SYNC_STALE, dispatch_sync
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import DriveFolder, KnowledgeDocument

router = APIRouter(
    prefix="/knowledge/drive-folders", tags=["knowledge"], dependencies=[Depends(local_only)]
)
# How each refusal from Drive is answered when a folder is connected.
CONNECT_STATUS = {
    "drive_folder_invalid": 422,
    "drive_not_a_folder": 422,
    "drive_not_shared": 404,
    "drive_not_configured": 503,
    "drive_key_invalid": 503,
    "drive_unavailable": 503,
}


class FolderConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    folder: str = Field(min_length=1, max_length=2048)
    kind: Literal["knowledge", "sample_posts"] = "knowledge"


def owned(folder_id: UUID, session, lock=False):
    query = select(DriveFolder).where(
        DriveFolder.id == folder_id,
        DriveFolder.user_id == LOCAL_USER_ID,
        DriveFolder.workspace_id == LOCAL_WORKSPACE_ID,
    )
    folder = session.scalar(query.with_for_update() if lock else query)
    if folder is None:
        raise HTTPException(404, "drive_folder_not_found")
    return folder


def syncing(folder) -> bool:
    """Queued or running. One older than SYNC_STALE was lost with its worker or broker."""
    started = folder.attempted_at if folder.sync_status == "Syncing" else folder.updated_at
    return (
        folder.sync_status in ("Pending", "Syncing")
        and started is not None
        and datetime.now(UTC) - started < SYNC_STALE
    )


def summary(folder, session):
    lost = folder.sync_status in ("Pending", "Syncing") and not syncing(folder)
    return {
        "id": str(folder.id),
        "folder_id": folder.folder_id,
        "name": folder.name,
        "kind": folder.kind,
        # A lost run shows as failed; Refresh or the next daily sync starts again.
        "status": "Failed" if lost else folder.sync_status,
        "error_code": "drive_sync_interrupted" if lost else folder.error_code,
        "synced_at": folder.synced_at.isoformat() if folder.synced_at else None,
        "attempted_at": folder.attempted_at.isoformat() if folder.attempted_at else None,
        "file_count": folder.file_count,
        "skipped_count": folder.skipped_count,
        "document_count": session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.drive_folder_id == folder.id,
                KnowledgeDocument.replaces_id.is_(None),
            )
        ),
    }


@router.get("")
def list_folders():
    with SessionLocal() as session:
        folders = session.scalars(
            select(DriveFolder)
            .where(
                DriveFolder.user_id == LOCAL_USER_ID,
                DriveFolder.workspace_id == LOCAL_WORKSPACE_ID,
            )
            .order_by(DriveFolder.created_at, DriveFolder.id)
        )
        return {
            "configured": drive.configured(),
            # The address the owner shares folders with; not a secret.
            "service_account_email": drive.service_account_email(),
            "items": [summary(folder, session) for folder in folders],
        }


@router.post("", status_code=202)
def connect_folder(payload: FolderConnection):
    try:
        folder_id = drive.folder_id(payload.folder)
        if not drive.configured():
            raise DriveError("drive_not_configured")
        name = drive.folder_name(folder_id)
    except DriveError as exc:
        raise HTTPException(CONNECT_STATUS.get(exc.code, 502), exc.code) from None
    with SessionLocal.begin() as session:
        seed_local_scope(session)
        row_id = session.scalar(
            insert(DriveFolder)
            .values(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                folder_id=folder_id,
                name=name,
                kind=payload.kind,
                sync_status="Pending",
                file_count=0,
                skipped_count=0,
            )
            .on_conflict_do_nothing()
            .returning(DriveFolder.id)
        )
        if row_id is None:
            existing = session.scalar(
                select(DriveFolder).where(
                    DriveFolder.workspace_id == LOCAL_WORKSPACE_ID,
                    DriveFolder.folder_id == folder_id,
                )
            )
            return {**summary(existing, session), "duplicate": True}
    dispatch_sync(row_id)
    with SessionLocal() as session:
        return {**summary(owned(row_id, session), session), "duplicate": False}


@router.post("/{folder_id}/sync", status_code=202)
def sync_now(folder_id: UUID):
    """Refresh: new and changed files come in, removed ones go. Unchanged files cost nothing."""
    with SessionLocal.begin() as session:
        folder = owned(folder_id, session, lock=True)
        if syncing(folder):
            return summary(folder, session)
        folder.sync_status = "Pending"
        folder.error_code = None
    dispatch_sync(folder_id)
    with SessionLocal() as session:
        return summary(owned(folder_id, session), session)


@router.delete("/{folder_id}")
def disconnect_folder(folder_id: UUID):
    """Removes the folder and every source that came from it. Nothing changes in Drive."""
    with SessionLocal.begin() as session:
        owned(folder_id, session, lock=True)
        keys = list(
            session.scalars(
                select(KnowledgeDocument.storage_key).where(
                    KnowledgeDocument.drive_folder_id == folder_id,
                    KnowledgeDocument.storage_key.is_not(None),
                )
            )
        )
        # Its sources, their staging copies, chunks and jobs go with it (ON DELETE CASCADE).
        session.execute(delete(DriveFolder).where(DriveFolder.id == folder_id))
    # After commit: a failure here leaves an unreferenced private file, never a dangling row.
    for key in keys:
        if key:
            storage.remove(key)
    return {"deleted": True}
