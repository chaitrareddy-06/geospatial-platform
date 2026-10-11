"""Real requests show up in /metrics under their route template."""

from __future__ import annotations


def sample(text: str, series: str) -> float:
    for line in text.splitlines():
        if line.startswith(series + " "):
            return float(line.split()[-1])
    return 0.0


def scrape(client) -> str:
    return client.get("/api/v1/metrics").text


def test_health_request_is_counted(client):
    series = 'api_request_total{method="GET",path="/api/v1/health",status="200"}'
    before = sample(scrape(client), series)

    assert client.get("/api/v1/health").status_code == 200

    assert sample(scrape(client), series) == before + 1


def test_label_is_the_route_template_not_the_raw_id(client):
    series = 'api_error_total{method="GET",path="/api/v1/files/{file_id}/",status="404"}'
    before = sample(scrape(client), series)

    assert client.get("/api/v1/files/does-not-exist-123/").status_code == 404

    text = scrape(client)
    assert sample(text, series) == before + 1
    assert "does-not-exist-123" not in text


def test_unknown_url_is_counted_as_unmatched(client):
    series = 'api_request_total{method="GET",path="unmatched",status="404"}'
    before = sample(scrape(client), series)

    assert client.get("/no/such/page").status_code == 404

    assert sample(scrape(client), series) == before + 1