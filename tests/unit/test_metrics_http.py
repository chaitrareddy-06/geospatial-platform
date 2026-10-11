"""HTTP request metrics: counts, latency and errors."""

from __future__ import annotations

from app.infrastructure.metrics.registry import Metrics


def sample(metrics: Metrics, series: str) -> float | None:
    for line in metrics.render().decode().splitlines():
        if line.startswith(series + " "):
            return float(line.split()[-1])
    return None


def test_request_is_counted_with_method_path_and_status():
    metrics = Metrics()
    metrics.record_request(
        method="GET", path="/api/v1/files/{file_id}/", status_code=200, duration_seconds=0.02
    )
    series = 'api_request_total{method="GET",path="/api/v1/files/{file_id}/",status="200"}'
    assert sample(metrics, series) == 1.0


def test_request_duration_is_observed_in_the_histogram():
    metrics = Metrics()
    metrics.record_request(
        method="GET", path="/x", status_code=200, duration_seconds=0.03
    )
    series = 'api_request_duration_seconds_count{method="GET",path="/x"}'
    assert sample(metrics, series) == 1.0


def test_error_status_is_counted_as_an_error():
    metrics = Metrics()
    metrics.record_request(
        method="POST", path="/x", status_code=500, duration_seconds=0.01
    )
    assert sample(metrics, 'api_error_total{method="POST",path="/x",status="500"}') == 1.0


def test_success_status_is_not_counted_as_an_error():
    metrics = Metrics()
    metrics.record_request(
        method="GET", path="/x", status_code=200, duration_seconds=0.01
    )
    assert sample(metrics, 'api_error_total{method="GET",path="/x",status="200"}') is None