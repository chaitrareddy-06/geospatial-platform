"""Job runners: how a QUEUED file gets processed.

Workers stay thin: they receive a job (file id + bytes), call the service and
let the service update the job state. Services never import this package.

Today: an in-process thread pool (no Redis needed). Later a Redis-backed
runner (ARQ or Celery) implements the same interface, so routes and services
do not change.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.services.file_service import FileService

logger = logging.getLogger(__name__)


class JobRunner(Protocol):
    def submit(self, file_id: str, content: bytes) -> None:
        """Schedule processing of a QUEUED file. Must not raise."""
        ...

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting jobs; optionally wait for running ones."""
        ...


def _execute(service: FileService, file_id: str, content: bytes) -> None:
    """Run one job. run_job records failures itself; this is the last safety net."""
    try:
        service.run_job(file_id, content)
    except Exception:  # noqa: BLE001 - a job error must never kill a worker thread
        logger.exception("job_runner_error", extra={"file_id": file_id})


class InlineJobRunner:
    """Runs the job immediately in the calling thread (tests, simple scripts)."""

    def __init__(self, service: FileService) -> None:
        self._service = service

    def submit(self, file_id: str, content: bytes) -> None:
        _execute(self._service, file_id, content)

    def shutdown(self, wait: bool = True) -> None:
        return None


class ThreadPoolJobRunner:
    """Runs jobs on a small pool of background threads."""

    def __init__(self, service: FileService, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._service = service
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="job-worker"
        )

    def submit(self, file_id: str, content: bytes) -> None:
        self._pool.submit(_execute, self._service, file_id, content)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)