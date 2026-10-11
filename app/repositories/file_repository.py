"""The storage interface the services depend on.

Services talk to this Protocol, never to a concrete store. Today there is an
in-memory implementation; after Step 3 a PostgreSQL one replaces it without
touching any service.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities.file_record import FileRecord


class FileRepository(Protocol):
    def add(self, record: FileRecord) -> None:
        """Store a new record."""
        ...

    def get(self, file_id: str) -> FileRecord | None:
        """Return the record, or None if the id is unknown."""
        ...

    def update(self, record: FileRecord) -> None:
        """Replace an existing record. Raises KeyError if the id is unknown."""
        ...

    def find_completed_by_sha256(self, sha256: str) -> FileRecord | None:
        """Return a COMPLETED record with this content hash, if any."""
        ...

    def list_unfinished(self) -> list[FileRecord]:
        """Return every record that is still QUEUED or PROCESSING."""
        ...