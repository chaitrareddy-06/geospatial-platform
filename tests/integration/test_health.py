from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get(f"{settings.api_v1_prefix}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == settings.app_name
    assert body["version"] == settings.app_version