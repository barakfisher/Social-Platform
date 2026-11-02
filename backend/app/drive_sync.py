"""Bring a shared Google Drive folder's files into the Knowledge Base (SP-30).

A sync lists the folder once and compares each file's Drive modifiedTime with the one last
imported, so an unchanged file is neither downloaded nor embedded again. A new file becomes
a source with the folder's kind. A changed file is loaded into a hidden staging copy, like a
web page loaded again (app/refresh.py), and replaces its original without asking: a
searchable original stays in use until the new chunks are embedded, and the kind the owner
chose stays. A file Google no longer lists in the folder is deleted. When the folder cannot
be listed nothing is deleted, and the next sync tries again.

Each folder syncs once a day (an hourly beat finds the due ones) and when the owner presses
Refresh. An advisory lock keeps one sync per folder at a time.
"""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app import drive, storage
from app.chunking import normalize_text
from app.db import SessionLocal
from app.drive import DriveError, DriveFile
from app.embeddings import configured as embeddings_configured
from app.embeddings import embedding_lock
from app.extraction import CONTROL_CHARACTERS, ExtractionError, decode_text_file
from app.knowledge import dispatch
from app.models import DriveFolder, IngestionJob, KnowledgeChunk, KnowledgeDocument
from app.refresh import ACTIVE, staging_for

# With an hourly check this syncs each folder about once a day without drifting later.
SYNC_INTERVAL = timedelta(hours=23)
# A sync still marked running after this was lost with its worker and may start again.
SYNC_STALE = timedelta(hours=1)
# Stages in which a source has text the new version must not take out of use early.
SETTLED = ("text_prepared", "ready", "embedding_failed")
logger = logging.getLogger(__name__)


@dataclass
class Content:
    text: str | None = None
    # A downloaded PDF in private storage; its text is extracted by the ingestion job.
    key: str | None = None
    failure: str | None = None


@dataclass
class Written:
    outcome: str
    # The stored PDF is referenced by a committed row.
    kept: bool = False
    job: tuple[UUID, UUID] | None = None
    stale_keys: tuple[str | None, ...] = ()


def read_content(file: DriveFile) -> Content:
    """Downloads one file. A transient DriveError propagates and stops the sync; any other
    failure is recorded on the source and tried again when the file changes."""
    try:
        data = drive.download(file)
    except DriveError as exc:
        if exc.transient:
            raise
        return Content(failure=exc.code)
    if not data:
        return Content(failure="source_empty")
    if file.form == "pdf":
        if not data.startswith(b"%PDF-"):
            return Content(failure="file_signature_mismatch")
        try:
            return Content(key=storage.put(data))
        except storage.StorageError as exc:
            raise DriveError(str(exc), transient=True) from None
    try:
        return Content(text=decode_text_file(data))
    except ExtractionError as exc:
        return Content(failure=exc.code)


def clean_name(file: DriveFile) -> str:
    return CONTROL_CHARACTERS.sub(" ", normalize_text(file.name)).strip()[:1000]


def title_for(file: DriveFile) -> str:
    name = clean_name(file)
    # A Google Doc's name has no extension, and a dot in it is part of the title.
    if file.form != "doc":
        name = PurePosixPath(name).stem or name
    return name[:300] or file.id


def fail(document, job, code: str) -> None:
    document.status = job.status = "Failed"
    document.processing_stage = "failed"
    document.error_code = job.error_code = code


def new_version(folder, file: DriveFile, content: Content, **values) -> KnowledgeDocument:
    return KnowledgeDocument(
        user_id=folder.user_id,
        workspace_id=folder.workspace_id,
        title=title_for(file),
        source_type="drive",
        source_reference=clean_name(file),
        source_text=content.text,
        storage_key=content.key,
        drive_folder_id=folder.id,
        drive_file_id=file.id,
        drive_modified_at=file.modified_time,
        status="Pending",
        **values,
    )


def text_job(session, document) -> IngestionJob:
    job = IngestionJob(
        user_id=document.user_id,
        workspace_id=document.workspace_id,
        document_id=document.id,
        request_id=str(uuid4()),
        kind="text_ingestion",
    )
    session.add(job)
    session.flush()
    return job


def locked_folder(session, folder_id: UUID):
    return session.scalar(select(DriveFolder).where(DriveFolder.id == folder_id).with_for_update())


def add(folder_id: UUID, file: DriveFile, content: Content) -> Written:
    with SessionLocal.begin() as session:
        folder = locked_folder(session, folder_id)
        if folder is None:  # Disconnected meanwhile.
            return Written("gone")
        document = new_version(folder, file, content, kind=folder.kind)
        session.add(document)
        session.flush()
        job = text_job(session, document)
        if content.failure:
            fail(document, job, content.failure)
            return Written("failed", kept=True)
        return Written("added", kept=True, job=(job.id, document.id))


def update(folder_id: UUID, document_id: UUID, file: DriveFile, content: Content) -> Written:
    with SessionLocal.begin() as session:
        folder = locked_folder(session, folder_id)
        document = session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update()
        )
        if folder is None or document is None:
            return Written("gone")
        staging = staging_for(session, document_id, lock=True)
        if staging is not None and staging.status in ACTIVE:
            return Written("waiting")
        stale: list[str | None] = []
        if staging is not None:
            # The last new version failed; this one takes its place.
            stale.append(staging.storage_key)
            session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == staging.id))
        if document.processing_stage in SETTLED:
            # The current text stays in use until the new version is ready (app/refresh.py).
            staging = new_version(folder, file, content, kind=document.kind)
            staging.replaces_id = document.id
            session.add(staging)
            session.flush()
            job = text_job(session, staging)
            if content.failure:
                fail(staging, job, content.failure)
                return Written("failed", kept=True, stale_keys=tuple(stale))
            return Written("updated", kept=True, job=(job.id, staging.id), stale_keys=tuple(stale))
        if document.status != "Failed":
            return Written("waiting", stale_keys=tuple(stale))
        # Never prepared (a failed import): the source itself takes the new version.
        stale.append(document.storage_key)
        document.title = title_for(file)
        document.source_reference = clean_name(file)
        document.source_text, document.storage_key = content.text, content.key
        document.drive_modified_at = file.modified_time
        document.status, document.processing_stage, document.error_code = "Pending", "pending", None
        session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == document.id, IngestionJob.kind == "text_ingestion")
            .with_for_update()
        ) or text_job(session, document)
        job.status, job.error_code = "Pending", None
        if content.failure:
            fail(document, job, content.failure)
            return Written("failed", kept=True, stale_keys=tuple(stale))
        return Written("updated", kept=True, job=(job.id, document.id), stale_keys=tuple(stale))


def needs_download(folder_id: UUID, file: DriveFile) -> tuple[bool, UUID | None, str]:
    """(download?, the existing source, outcome when not downloading)."""
    with SessionLocal() as session:
        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.drive_folder_id == folder_id,
                KnowledgeDocument.drive_file_id == file.id,
                KnowledgeDocument.replaces_id.is_(None),
            )
        )
        if document is None:
            return True, None, ""
        if document.drive_modified_at == file.modified_time:
            return False, document.id, "unchanged"
        staging = staging_for(session, document.id)
        if staging is not None:
            if staging.status in ACTIVE:
                return False, document.id, "waiting"
            if staging.processing_stage == "failed" and (
                staging.drive_modified_at == file.modified_time
            ):
                # This version could not be read; it is tried again once the file changes.
                return False, document.id, "failed"
        if document.processing_stage not in SETTLED and document.status != "Failed":
            return False, document.id, "waiting"
        if document.status == "Ready" and not embeddings_configured():
            # The new text could not be made searchable; the current one stays.
            return False, document.id, "waiting"
        return True, document.id, ""


def sync_file(folder_id: UUID, file: DriveFile) -> str:
    download, document_id, outcome = needs_download(folder_id, file)
    if not download:
        return outcome
    content = read_content(file)
    written = Written("gone")
    try:
        if document_id is None:
            written = add(folder_id, file, content)
        else:
            written = update(folder_id, document_id, file, content)
    finally:
        if content.key and not written.kept:
            storage.remove(content.key)
    for key in written.stale_keys:
        if key:
            storage.remove(key)
    if written.job:
        dispatch(*written.job)
    return written.outcome


def remove_missing(folder_id: UUID, listed: set[str]) -> int:
    """Deletes the sources of files Google no longer lists in the folder."""
    keys: list[str | None] = []
    with SessionLocal.begin() as session:
        documents = session.scalars(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.drive_folder_id == folder_id,
                KnowledgeDocument.replaces_id.is_(None),
                KnowledgeDocument.drive_file_id.not_in(sorted(listed)),
            )
            .with_for_update()
        ).all()
        for document in documents:
            keys.append(document.storage_key)
            staging = staging_for(session, document.id, lock=True)
            if staging is not None:
                keys.append(staging.storage_key)
            # Chunks, jobs and the staging copy go with it (ON DELETE CASCADE).
            session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document.id))
    for key in keys:
        if key:
            storage.remove(key)
    return len(documents)


def finish(folder_id: UUID, error: str | None, **listing) -> None:
    with SessionLocal.begin() as session:
        folder = locked_folder(session, folder_id)
        if folder is None:
            return
        folder.sync_status = "Failed" if error else "Ready"
        folder.error_code = error
        if listing:
            folder.name = listing["name"] or folder.name
            folder.file_count = listing["file_count"]
            folder.skipped_count = listing["skipped_count"]
            if not error:
                folder.synced_at = datetime.now(UTC)


def run(folder_id: UUID) -> None:
    with SessionLocal.begin() as session:
        folder = locked_folder(session, folder_id)
        if folder is None:
            return
        folder.sync_status = "Syncing"
        folder.attempted_at = datetime.now(UTC)
        drive_folder_id = folder.folder_id
    try:
        name = drive.folder_name(drive_folder_id)
        files = drive.list_folder(drive_folder_id)
    except DriveError as exc:
        # Nothing is deleted on a failed listing: the folder may only be out of reach.
        finish(folder_id, exc.code)
        logger.info(
            "drive_sync_failed",
            extra={"drive_folder_id": str(folder_id), "error_code": exc.code},
        )
        return
    wanted = {file.id: file for file in files if file.form}
    counts: Counter[str] = Counter()
    error = None
    for file in wanted.values():
        try:
            counts[sync_file(folder_id, file)] += 1
        except DriveError as exc:
            # Drive is out of reach for now; the rest waits for the next sync.
            error = exc.code
            break
    if error is None:
        # Last, so a sync that fails anywhere deletes nothing.
        counts["removed"] = remove_missing(folder_id, set(wanted))
    finish(
        folder_id,
        error,
        name=name,
        file_count=len(wanted),
        skipped_count=len(files) - len(wanted),
    )
    logger.info(
        "drive_sync_complete",
        extra={
            "drive_folder_id": str(folder_id),
            "error_code": error,
            "added_count": counts["added"],
            "updated_count": counts["updated"],
            "removed_count": counts["removed"],
            "unchanged_count": counts["unchanged"],
        },
    )


def sync_folder(folder_id: UUID) -> None:
    with embedding_lock(str(folder_id)) as acquired:
        if not acquired:
            return  # This folder is already syncing.
        try:
            run(folder_id)
        except Exception:
            finish(folder_id, "drive_sync_failed")
            raise


def due_folders() -> list[UUID]:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(DriveFolder.id).where(
                    DriveFolder.attempted_at.is_(None)
                    | (DriveFolder.attempted_at < now - SYNC_INTERVAL)
                )
            )
        )


def dispatch_sync(folder_id: UUID) -> None:
    from app.worker import sync_drive_folder

    try:
        sync_drive_folder.apply_async(args=[str(folder_id)])
    except Exception:
        finish(folder_id, "dispatch_failed")
