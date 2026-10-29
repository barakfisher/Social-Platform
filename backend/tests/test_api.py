from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")


def test_liveness_and_error_contract():
    response = client.get("/health/live")
    assert response.json() == {"status": "alive"}
    assert response.headers["x-request-id"]
    missing = client.get("/unknown")
    assert missing.status_code == 404
    assert missing.json()["error"]["request_id"] == missing.headers["x-request-id"]
    assert client.get("/dev/jobs/invalid-uuid").json()["error"]["code"] == "validation_error"


def test_readiness_hides_dependency_details():
    with patch("app.main.engine.connect", side_effect=RuntimeError("secret connection details")):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependencies_unavailable"
    assert "secret" not in response.text


def test_cors_restricts_origins():
    origin = get_settings().cors_origins[0]
    allowed = client.options(
        "/health/live",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    denied = client.options(
        "/health/live",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-origin" not in denied.headers
