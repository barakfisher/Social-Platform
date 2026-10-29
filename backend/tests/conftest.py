import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.local_scope import LOCAL_WORKSPACE_ID
from app.main import app
from app.models import KnowledgeDocument


@pytest.fixture
def api():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for Knowledge Base tests")
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        with factory.begin() as session:
            session.execute(
                delete(KnowledgeDocument).where(
                    KnowledgeDocument.workspace_id == LOCAL_WORKSPACE_ID
                )
            )
        with (
            patch("app.knowledge.SessionLocal", factory),
            patch("app.worker.SessionLocal", factory),
            patch("app.knowledge.process_text.apply_async") as dispatch,
        ):
            yield TestClient(app, base_url="http://127.0.0.1"), factory, dispatch
        transaction.rollback()
    engine.dispose()
