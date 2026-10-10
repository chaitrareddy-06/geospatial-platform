import pytest

from app.core.exceptions import (
    CorruptKMLError,
    CRSResolutionError,
    DuplicateFileError,
    EmptyFileError,
    ResourceNotFoundError,
    UnsupportedFileTypeError,
)
from app.domain.enums.job_status import JobStatus


def test_kml_upload_completes(make_service, kml_bytes):
    record = make_service().ingest("survey.kml", kml_bytes)
    assert record.status is JobStatus.COMPLETED
    assert record.feature_count == 3
    assert record.crs == "EPSG:4326"
    assert len(record.layers) == 1
    assert record.layers[0].measured_count == 3
    assert record.processing_ms is not None
    assert record.processing_ms >= 0
    assert record.error_code is None


def test_shapefile_zip_upload_completes(make_service, shapefile_zip):
    record = make_service().ingest("parcels.zip", shapefile_zip())
    assert record.status is JobStatus.COMPLETED
    assert record.feature_count == 2
    assert record.crs is not None
    assert "4326" in record.crs or "WGS" in record.crs


def test_finished_record_can_be_fetched_again(make_service, kml_bytes):
    service = make_service()
    record = service.ingest("survey.kml", kml_bytes)
    assert service.get(record.id) == record


def test_get_unknown_id_raises_not_found(make_service):
    with pytest.raises(ResourceNotFoundError):
        make_service().get("does-not-exist")


def test_duplicate_of_completed_upload_is_rejected(make_service, kml_bytes):
    service = make_service()
    first = service.ingest("survey.kml", kml_bytes)
    with pytest.raises(DuplicateFileError) as excinfo:
        service.ingest("copy-of-survey.kml", kml_bytes)
    assert excinfo.value.details["existing_id"] == first.id


def test_failed_upload_can_be_retried(make_service, shapefile_zip):
    service = make_service()
    content = shapefile_zip(None)
    first = service.ingest("parcels.zip", content)
    second = service.ingest("parcels.zip", content)
    assert first.status is JobStatus.FAILED
    assert second.status is JobStatus.FAILED
    assert second.id != first.id


def test_missing_crs_is_recorded_as_failed(make_service, shapefile_zip):
    record = make_service().ingest("parcels.zip", shapefile_zip(None))
    assert record.status is JobStatus.FAILED
    assert record.error_code == CRSResolutionError.error_code
    assert record.error_reason == "missing_crs"
    assert record.completed_at is not None


def test_missing_crs_can_be_assumed_when_enabled(make_service, shapefile_zip):
    service = make_service(assume_wgs84_if_missing=True)
    record = service.ingest("parcels.zip", shapefile_zip(None))
    assert record.status is JobStatus.COMPLETED
    assert any("EPSG:4326" in warning for warning in record.warnings)


def test_corrupt_kml_is_recorded_as_failed(make_service):
    record = make_service().ingest("bad.kml", b"<kml><broken")
    assert record.status is JobStatus.FAILED
    assert record.error_code == CorruptKMLError.error_code


def test_unexpected_crash_is_recorded_without_leaking_details(
    make_service, kml_bytes, monkeypatch
):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom secret detail")

    monkeypatch.setattr("app.services.file_service.process_dataset", boom)
    record = make_service().ingest("survey.kml", kml_bytes)
    assert record.status is JobStatus.FAILED
    assert record.error_code == "internal_error"
    assert "kaboom" not in (record.error_message or "")


def test_empty_upload_is_rejected_before_anything_is_stored(make_service):
    with pytest.raises(EmptyFileError):
        make_service().ingest("survey.kml", b"")


def test_unsupported_extension_is_rejected(make_service):
    with pytest.raises(UnsupportedFileTypeError):
        make_service().ingest("notes.txt", b"hello")