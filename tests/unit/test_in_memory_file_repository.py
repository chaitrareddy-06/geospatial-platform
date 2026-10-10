from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domain.entities.file_record import FileRecord
from app.domain.enums.file_kind import FileKind
from app.domain.enums.job_status import JobStatus
from app.repositories.in_memory_file_repository import InMemoryFileRepository


def _record(file_id="f1", sha256="abc", status=JobStatus.PROCESSING) -> FileRecord:
    return FileRecord(
        id=file_id,
        filename="a.kml",
        kind=FileKind.KML,
        size_bytes=10,
        sha256=sha256,
        status=status,
        created_at=datetime.now(UTC),
    )


def test_add_then_get_returns_the_record():
    repo = InMemoryFileRepository()
    record = _record()
    repo.add(record)
    assert repo.get("f1") == record


def test_get_unknown_id_returns_none():
    assert InMemoryFileRepository().get("missing") is None


def test_update_replaces_the_record():
    repo = InMemoryFileRepository()
    repo.add(_record())
    repo.update(replace(_record(), status=JobStatus.COMPLETED))
    assert repo.get("f1").status is JobStatus.COMPLETED


def test_update_unknown_id_raises_key_error():
    with pytest.raises(KeyError):
        InMemoryFileRepository().update(_record("nope"))


def test_find_completed_by_sha256_ignores_unfinished_and_failed():
    repo = InMemoryFileRepository()
    repo.add(_record("p", sha256="same", status=JobStatus.PROCESSING))
    repo.add(_record("f", sha256="same", status=JobStatus.FAILED))
    assert repo.find_completed_by_sha256("same") is None

    repo.add(_record("c", sha256="same", status=JobStatus.COMPLETED))
    found = repo.find_completed_by_sha256("same")
    assert found is not None
    assert found.id == "c"
    assert repo.find_completed_by_sha256("other") is None