from __future__ import annotations

import threading

from app.domain.entities.file_record import FileRecord
from app.domain.enums.job_status import JobStatus


class InMemoryFileRepository:
    """Dictionary-backed store. Data is lost on restart (fine until Step 3).

    A lock protects the dictionary because FastAPI runs sync endpoints in
    a thread pool, so several requests can touch it at once.
    """

    def __init__(self) -> None:
        self._records: dict[str, FileRecord] = {}
        self._lock = threading.Lock()

    def add(self, record: FileRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def get(self, file_id: str) -> FileRecord | None:
        with self._lock:
            return self._records.get(file_id)

    def update(self, record: FileRecord) -> None:
        with self._lock:
            if record.id not in self._records:
                raise KeyError(record.id)
            self._records[record.id] = record

    def find_completed_by_sha256(self, sha256: str) -> FileRecord | None:
        with self._lock:
            for record in self._records.values():
                if record.sha256 == sha256 and record.status is JobStatus.COMPLETED:
                    return record
        return None