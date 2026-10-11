"""What the file service tells the outside world while it works.

The service calls these methods at key moments. Who listens (metrics,
audit log, ...) is decided by the caller, so the service never imports
Prometheus or any other infrastructure.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.entities.file_record import FileRecord
from app.services.dataset_processing import DatasetResult


class ProcessingObserver(Protocol):
    def upload_accepted(self, record: FileRecord) -> None:
        """A valid, non-duplicate upload was stored as QUEUED."""
        ...

    def dataset_processed(self, result: DatasetResult) -> None:
        """One dataset of a file that finished COMPLETED."""
        ...

    def job_finished(self, record: FileRecord) -> None:
        """A job reached a final state (COMPLETED or FAILED, incl. swept)."""
        ...