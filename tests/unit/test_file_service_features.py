import pytest

from app.core.exceptions import ResourceNotFoundError
from app.domain.enums.job_status import JobStatus
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService


def _service() -> FileService:
    return FileService(
        InMemoryFileRepository(),
        feature_repository=InMemoryFeatureResultRepository(),
        assume_wgs84_if_missing=False,
        max_utm_offset_deg=4.0,
        max_upload_size_bytes=50 * 1024 * 1024,
    )


def test_completed_file_stores_its_features(kml_bytes):
    service = _service()
    record = service.ingest("survey.kml", kml_bytes)
    assert record.status is JobStatus.COMPLETED

    _, page = service.list_measurements(record.id)
    assert page.total == record.feature_count == 3
    kinds = {item.feature.kind.value for item in page.items}
    assert len(kinds) == 3  # polygon, line, point


def test_failed_file_stores_no_features(shapefile_zip):
    service = _service()
    record = service.ingest("nocrs.zip", shapefile_zip(crs=None))
    assert record.status is JobStatus.FAILED

    _, page = service.list_measurements(record.id)
    assert page.total == 0


def test_list_measurements_unknown_id_raises():
    with pytest.raises(ResourceNotFoundError):
        _service().list_measurements("does-not-exist")


def test_list_measurements_pages_through_service(kml_bytes):
    service = _service()
    record = service.ingest("survey.kml", kml_bytes)
    _, page = service.list_measurements(record.id, offset=1, limit=1)
    assert page.total == 3
    assert len(page.items) == 1