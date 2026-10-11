"""The /metrics endpoint exposes the Prometheus text format."""


def test_versioned_metrics_endpoint(client):
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "files_uploaded_total" in response.text


def test_plain_metrics_alias_returns_the_same_format(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "queue_size" in response.text