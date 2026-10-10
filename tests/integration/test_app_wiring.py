from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_response_has_generated_request_id():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert len(resp.headers["X-Request-ID"]) == 32


def test_client_supplied_request_id_is_echoed_back():
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "my-trace-1"})
    assert resp.headers["X-Request-ID"] == "my-trace-1"


def test_unknown_route_returns_standard_error_shape():
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_404"