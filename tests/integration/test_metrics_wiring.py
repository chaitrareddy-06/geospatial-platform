"""Real uploads through HTTP show up on /metrics."""

from __future__ import annotations

from app.domain.enums.job_status import JobStatus
from app.infrastructure.metrics.observer import MetricsObserver
from app.infrastructure.metrics.registry import get_metrics
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService
from app.workers.job_runner import RunnerStats


def sample(text: str, series: str) -> float:
    for line in text.splitlines():
        if line.startswith(series + " "):
            return float(line.split()[-1])
    return 0.0


class StubRunner:
    def submit(self, file_id: str, content: bytes) -> None:
        pass

    def shutdown(self, wait: bool = True) -> None:
        pass

    def stats(self) -> RunnerStats:
        return RunnerStats(workers=2, queued=5, active=2, finished=0, errors=0)


def test_upload_through_http_increments_the_counters(make_client, kml_bytes):
    # The app's metrics object is shared by all tests, so compare before/after.
    service = FileService(
        InMemoryFileRepository(),
        feature_repository=InMemoryFeatureResultRepository(),
        assume_wgs84_if_missing=False,
        max_utm_offset_deg=4.0,
        max_upload_size_bytes=50 * 1024 * 1024,
        observer=MetricsObserver(get_metrics()),
    )
    client = make_client(service=service)
    names = ("files_uploaded_total", "processing_jobs_success_total", "features_processed_total")
    before = {n: sample(client.get("/api/v1/metrics").text, n) for n in names}

    response = client.post(
        "/api/v1/files/", files={"file": ("a.kml", kml_bytes, "application/octet-stream")}
    )
    assert response.status_code == 202
    assert service.get(response.json()["id"]).status is JobStatus.COMPLETED

    after = {n: sample(client.get("/api/v1/metrics").text, n) for n in names}
    assert after["files_uploaded_total"] == before["files_uploaded_total"] + 1
    assert after["processing_jobs_success_total"] == before["processing_jobs_success_total"] + 1
    assert after["features_processed_total"] == before["features_processed_total"] + 3


def test_scrape_refreshes_queue_and_active_gauges(make_client):
    client = make_client(runner=StubRunner())
    text = client.get("/api/v1/metrics").text
    assert sample(text, "queue_size") == 5.0
    assert sample(text, "active_jobs") == 2.0