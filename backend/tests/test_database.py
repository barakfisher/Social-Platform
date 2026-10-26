import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.models import IngestionJob, KnowledgeChunk, KnowledgeDocument, Post, User, Workspace
from app.worker import foundation_probe

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a migrated PostgreSQL database",
)


@pytest.fixture
def db():
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


def scope(db):
    user = User(name="test")
    db.add(user)
    db.flush()
    workspace = Workspace(user_id=user.id, name="test")
    db.add(workspace)
    db.flush()
    return {"user_id": user.id, "workspace_id": workspace.id}


def test_ownership_vector_and_document_deletion(db):
    owner = scope(db)
    other = scope(db)
    document = KnowledgeDocument(**owner, title="מקור", source_type="text")
    db.add(document)
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            KnowledgeChunk(
                **other, document_id=document.id, chunk_order=0, content="bad", token_count=1
            )
        )
        db.flush()
    chunk = KnowledgeChunk(
        **owner,
        document_id=document.id,
        chunk_order=0,
        content="שלום",
        token_count=1,
        embedding=[1, 0, 0],
        embedding_model="test-only",
        embedding_dimensions=3,
    )
    db.add(chunk)
    db.add(
        Post(
            **owner,
            platform="linkedin",
            language="he",
            content="טיוטה",
            source_snapshots=[{"title": document.title, "excerpt": "שלום"}],
        )
    )
    db.flush()
    assert db.scalar(
        select(KnowledgeChunk.embedding.cosine_distance([1, 0, 0])).where(
            KnowledgeChunk.document_id == document.id
        )
    ) == pytest.approx(0)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            KnowledgeChunk(
                **owner,
                document_id=document.id,
                chunk_order=1,
                content="bad",
                token_count=1,
                embedding=[1, 0],
                embedding_dimensions=3,
                embedding_model="test-only",
            )
        )
        db.flush()
    db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document.id))
    assert (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.workspace_id == owner["workspace_id"])
        )
        == 0
    )
    assert (
        db.scalar(select(Post).where(Post.workspace_id == owner["workspace_id"])).source_snapshots[
            0
        ]["excerpt"]
        == "שלום"
    )


def test_phase_one_rejects_publishing(db):
    owner = scope(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Post(**owner, platform="facebook", language="en", content="draft", status="Published")
        )
        db.flush()


def test_runtime_cannot_create_tables(db):
    assert db.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")) is False
    with pytest.raises(ProgrammingError), db.begin_nested():
        db.execute(text("CREATE TABLE should_not_be_allowed (id integer)"))


def test_worker_repeated_delivery_is_idempotent(db):
    # A separate committed job is required because the worker opens its own connection.
    from app.db import SessionLocal

    with SessionLocal.begin() as session:
        owner = scope(session)
        job = IngestionJob(**owner, request_id=str(uuid4()), kind="foundation_probe")
        session.add(job)
        session.flush()
        job_id, user_id = str(job.id), owner["user_id"]
    try:
        foundation_probe(job_id)
        foundation_probe(job_id)
        with SessionLocal() as session:
            stored = session.get(IngestionJob, job.id)
            assert stored.status == "Ready"
            assert stored.attempts == 1
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(Workspace).where(Workspace.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
