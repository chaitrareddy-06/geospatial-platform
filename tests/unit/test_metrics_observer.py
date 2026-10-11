"""The metrics adapter turns service events into Prometheus numbers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.domain.entities.file_record import FileRecord
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus
from app.infrastructure.metrics.observer import MetricsObserver
from app.infrastructure.metrics.registry import Metrics
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService


def sample(metrics: Metrics, series: str) -> float | None:
    """Value of one exposed line such as 'files_uploaded_total' or
    'processing_jobs_failed_total{reason="x"}'; None if the line is absent."""
    for line in metrics.render().decode().splitlines():
        if line.startswith(series + " "):
            return float(line.split()[-1])
    return None


def make_record(**changes) -> FileRecord:
    base = FileRecord(
        id="abc",
        filename="a.kml",
        kind=FileKind.KML,
        size_bytes=1234,
        sha256="0" * 64,
        status=JobStatus.QUEUED,
        created_at=datetime.now(UTC),
    )
    return replace(base, **changes)


def test_accepted_upload_increments_files_uploaded():
    metrics = Metrics()
    MetricsObserver(metrics).upload_accepted(make_record())
    assert sample(metrics, "files_uploaded_total") == 1.0


def test_completed_job_increments_success():
    metrics = Metrics()
    record = make_record(status=JobStatus.COMPLETED, processing_ms=250.0)
    MetricsObserver(metrics).job_finished(record)
    assert sample(metrics, "processing_jobs_success_total") == 1.0


def test_failed_job_is_counted_with_its_reason():
    metrics = Metrics()
    record = make_record(
        status=JobStatus.FAILED,
        error_code="geometry_processing_failed",
        error_reason="no_datasets",
    )
    MetricsObserver(metrics).job_finished(record)
    assert (
        sample(metrics, 'processing_jobs_failed_total{reason="no_datasets"}') == 1.0
    )


def test_crs_failure_is_counted_by_reason():
    metrics = Metrics()
    record = make_record(
        status=JobStatus.FAILED,
        error_code="crs_resolution_failed",
        error_reason="missing_crs",
    )
    MetricsObserver(metrics).job_finished(record)
    assert (
        sample(metrics, 'crs_resolution_failures_total{reason="missing_crs"}') == 1.0
    )


def test_real_upload_end_to_end_updates_the_counters(kml_bytes):
    metrics = Metrics()
    service = FileService(
        InMemoryFileRepository(),
        feature_repository=InMemoryFeatureResultRepository(),
        assume_wgs84_if_missing=False,
        max_utm_offset_deg=4.0,
        max_upload_size_bytes=50 * 1024 * 1024,
        observer=MetricsObserver(metrics),
    )
    record = service.ingest("a.kml", kml_bytes)
    assert record.status is JobStatus.COMPLETED
    assert sample(metrics, "files_uploaded_total") == 1.0
    assert sample(metrics, "processing_jobs_success_total") == 1.0
    assert sample(metrics, "features_processed_total") == 3.0