import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.core.exceptions import FileTooLargeError, ResourceNotFoundError


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/too-large")
    def too_large():
        raise FileTooLargeError(details={"limit_mb": 50})

    @app.get("/missing")
    def missing():
        raise ResourceNotFoundError()

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"item_id": item_id}

    @app.get("/crash")
    def crash():
        raise RuntimeError("secret internal detail")

    # raise_server_exceptions=False lets us see the 500 response instead of the raw crash
    return TestClient(app, raise_server_exceptions=False)


def test_app_error_uses_its_own_status_code_and_shape(client):
    resp = client.get("/too-large")
    assert resp.status_code == 413
    assert resp.json() == {
        "error": {
            "code": "file_too_large",
            "message": "The uploaded file exceeds the maximum allowed size.",
            "details": {"limit_mb": 50},
        }
    }


def test_app_error_without_details_returns_empty_details(client):
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert resp.json()["error"]["details"] == {}


def test_request_validation_error_is_reshaped(client):
    resp = client.get("/items/not-a-number")
    body = resp.json()
    assert resp.status_code == 422
    assert body["error"]["code"] == "request_validation_failed"
    assert isinstance(body["error"]["details"]["errors"], list)


def test_unknown_route_uses_same_shape(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_404"


def test_unexpected_crash_returns_safe_500(client):
    resp = client.get("/crash")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in resp.text