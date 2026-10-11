import pytest

from app.core.exceptions import DuplicateFileError, ResourceNotFoundError
from app.domain.enums.job_status import JobStatus


def test_submit_returns_a_queued_record_and_does_no_processing(make_service, kml_bytes):
    service = make_service()
    record = service.submit("survey.kml", kml_bytes)

    assert record.status is JobStatus.QUEUED
    assert service.get(record.id).status is JobStatus.QUEUED
    _, page = service.list_measurements(record.id)
    assert page.total == 0


def test_run_job_completes_a_queued_record(make_service, kml_bytes):
    service = make_service()
    queued = service.submit("survey.kml", kml_bytes)

    done = service.run_job(queued.id, kml_bytes)

    assert done.status is JobStatus.COMPLETED
    assert done.feature_count == 3
    _, page = service.list_measurements(queued.id)
    assert page.total == 3


def test_run_job_twice_does_not_process_again(make_service, kml_bytes):
    service = make_service()
    queued = service.submit("survey.kml", kml_bytes)
    service.run_job(queued.id, kml_bytes)

    again = service.run_job(queued.id, kml_bytes)

    assert again.status is JobStatus.COMPLETED
    _, page = service.list_measurements(queued.id)
    assert page.total == 3  # features were not stored a second time


def test_run_job_unknown_id_raises(make_service, kml_bytes):
    with pytest.raises(ResourceNotFoundError):
        make_service().run_job("does-not-exist", kml_bytes)


def test_duplicate_is_rejected_after_the_first_completes(make_service, kml_bytes):
    service = make_service()
    service.ingest("survey.kml", kml_bytes)
    with pytest.raises(DuplicateFileError):
        service.submit("again.kml", kml_bytes)