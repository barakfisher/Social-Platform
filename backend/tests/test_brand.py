import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.brand import get_session
from app.config import get_settings
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID
from app.main import app
from app.models import BrandDNA, User, Workspace


@pytest.fixture
def brand_client():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for Brand DNA persistence tests")
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:

            def override():
                yield session

            app.dependency_overrides[get_session] = override
            try:
                yield TestClient(app, base_url="http://127.0.0.1"), session
            finally:
                app.dependency_overrides.pop(get_session, None)
        transaction.rollback()
    engine.dispose()


def test_brand_create_update_roundtrip_and_conflict(brand_client):
    client, session = brand_client
    # Isolate the local profile; the outer transaction restores development data.
    from sqlalchemy import delete

    session.execute(delete(BrandDNA).where(BrandDNA.workspace_id == LOCAL_WORKSPACE_ID))
    assert client.get("/brand").json() is None
    payload = {"name": "  מותג בדיקה  ", "audience": "English ועברית", "version": 0}
    created = client.put("/brand", json=payload)
    assert created.status_code == 200
    assert created.json()["name"] == "מותג בדיקה"
    assert created.json()["version"] == 1
    assert client.get("/brand").json() == created.json()
    duplicate = client.put("/brand", json=payload)
    assert duplicate.status_code == 409
    updated = client.put("/brand", json={**created.json(), "voice": "Warm and clear"})
    assert updated.json()["version"] == 2
    assert client.get("/brand").json()["voice"] == "Warm and clear"
    assert client.put("/brand", json=created.json()).status_code == 409
    record = session.scalar(select(BrandDNA).where(BrandDNA.workspace_id == LOCAL_WORKSPACE_ID))
    assert record.user_id == LOCAL_USER_ID


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   ", "version": 0},
        {"name": "x" * 201, "version": 0},
        {"name": "Brand", "version": -1},
        {"name": "Brand", "version": 0, "user_id": str(uuid4())},
        {"name": "Brand", "version": 0, "guidelines": "x" * 10001},
    ],
)
def test_brand_validation(payload):
    # Rejects invalid input before opening a database transaction.
    app.dependency_overrides[get_session] = lambda: None
    try:
        response = TestClient(app, base_url="http://127.0.0.1").put("/brand", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_brand_cannot_read_or_update_other_owner(brand_client):
    client, session = brand_client
    user = User(name="Other")
    session.add(user)
    session.flush()
    workspace = Workspace(name="Other", user_id=user.id)
    session.add(workspace)
    session.flush()
    other = BrandDNA(user_id=user.id, workspace_id=workspace.id, name="Private other brand")
    session.add(other)
    session.flush()
    before = client.get("/brand").json()
    assert before is None or before["name"] != "Private other brand"
    client.put("/brand", json={"name": "My brand", "version": before["version"] if before else 0})
    session.refresh(other)
    assert other.name == "Private other brand"


def test_production_cannot_use_fixed_identity():
    settings = get_settings()
    previous = settings.environment
    settings.environment = "production"
    app.dependency_overrides[get_session] = lambda: None
    try:
        assert TestClient(app, base_url="http://127.0.0.1").get("/brand").status_code == 503
        assert (
            TestClient(app, base_url="http://127.0.0.1")
            .put("/brand", json={"name": "Brand", "version": 0})
            .status_code
            == 503
        )
    finally:
        settings.environment = previous
        app.dependency_overrides.pop(get_session, None)
