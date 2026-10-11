"""The stale-job guard: unfinished records past a time limit become FAILED."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.entities.file_record import FileRecord
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus
from app.repositories.in_memory_file_repository import InMemoryFileRepository
from app.services.file_service import FileService

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
LIMIT = 600.0  # seconds


def _service(repository):
    return FileService(
        repository,
        assume_wgs84_if_missing=False,
        max_utm_offset_deg=4.0,
        max_upload_size_bytes=50 * 1024 * 1024,
    )


def _record(file_id, status, age_seconds):
    return FileRecord(
        id=file_id,
        filename=f"{file_id}.kml",
        kind=FileKind.KML,
        size_bytes=10,
        sha256=f"hash-{file_id}",
        status=status,
        created_at=NOW - timedelta(seconds=age_seconds),
    )


def test_list_unfinished_returns_only_queued_and_processing():
    repo = InMemoryFileRepository()
    repo.add(_record("q", JobStatus.QUEUED, 1))
    repo.add(_record("p", JobStatus.PROCESSING, 1))
    repo.add(_record("c", JobStatus.COMPLETED, 1))
    repo.add(_record("f", JobStatus.FAILED, 1))

    ids = {r.id for r in repo.list_unfinished()}

    assert ids == {"q", "p"}


def test_fresh_job_is_left_alone():
    repo = InMemoryFileRepository()
    repo.add(_record("a", JobStatus.QUEUED, LIMIT - 1))
    service = _service(repo)

    failed = service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    assert failed == 0
    assert repo.get("a").status is JobStatus.QUEUED


def test_old_queued_job_fails_as_stale_queued():
    repo = InMemoryFileRepository()
    repo.add(_record("a", JobStatus.QUEUED, LIMIT + 1))
    service = _service(repo)

    failed = service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    record = repo.get("a")
    assert failed == 1
    assert record.status is JobStatus.FAILED
    assert record.error_code == "job_timed_out"
    assert record.error_reason == "stale_queued"
    assert record.completed_at == NOW


def test_old_processing_job_fails_as_stale_processing():
    repo = InMemoryFileRepository()
    repo.add(_record("a", JobStatus.PROCESSING, LIMIT + 1))
    service = _service(repo)

    service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    record = repo.get("a")
    assert record.status is JobStatus.FAILED
    assert record.error_code == "job_timed_out"
    assert record.error_reason == "stale_processing"


def test_finished_records_are_never_touched():
    repo = InMemoryFileRepository()
    repo.add(_record("c", JobStatus.COMPLETED, LIMIT * 10))
    repo.add(_record("f", JobStatus.FAILED, LIMIT * 10))
    service = _service(repo)

    failed = service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    assert failed == 0
    assert repo.get("c").status is JobStatus.COMPLETED
    assert repo.get("f").status is JobStatus.FAILED
    assert repo.get("f").error_code is None


def test_returns_how_many_were_failed():
    repo = InMemoryFileRepository()
    repo.add(_record("old1", JobStatus.QUEUED, LIMIT + 5))
    repo.add(_record("old2", JobStatus.PROCESSING, LIMIT + 5))
    repo.add(_record("new", JobStatus.QUEUED, 1))
    service = _service(repo)

    failed = service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    assert failed == 2
    assert repo.get("new").status is JobStatus.QUEUED


@pytest.mark.parametrize("bad_limit", [0, -1])
def test_non_positive_max_age_is_rejected(bad_limit):
    service = _service(InMemoryFileRepository())

    with pytest.raises(ValueError):
        service.fail_stale_jobs(max_age_seconds=bad_limit, now=NOW)


def test_a_swept_job_is_not_run_afterwards():
    repo = InMemoryFileRepository()
    repo.add(_record("a", JobStatus.QUEUED, LIMIT + 1))
    service = _service(repo)
    service.fail_stale_jobs(max_age_seconds=LIMIT, now=NOW)

    # A late worker still holds the bytes. run_job must leave the FAILED record alone.
    result = service.run_job("a", b"not even parsed")

    assert result.status is JobStatus.FAILED
    assert result.error_code == "job_timed_out"