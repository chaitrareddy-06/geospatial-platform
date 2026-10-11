"""Job runners: how a QUEUED file gets processed.

Workers stay thin: they receive a job (file id + bytes), call the service and
let the service update the job state. Services never import this package.

Today: an in-process thread pool (no Redis needed). Later a Redis-backed
runner (ARQ or Celery) implements the same interface, so routes and services
do not change.

Each runner also counts its own work (queued, active, finished, errors) and
reports it through ``stats()``. Pure services stay free of metrics code; the
metrics layer (Step 12) reads these numbers.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from app.services.file_service import FileService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunnerStats:
    """A snapshot of one runner's workload."""

    workers: int
    queued: int  # waiting for a worker
    active: int  # running right now
    finished: int  # done, whether the file succeeded or not
    errors: int  # jobs where an exception escaped run_job (the safety net)


class JobRunner(Protocol):
    def submit(self, file_id: str, content: bytes) -> None:
        """Schedule processing of a QUEUED file. Must not raise."""
        ...

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting jobs; optionally wait for running ones."""
        ...

    def stats(self) -> RunnerStats:
        """Return a snapshot of queued / active / finished / error counts."""
        ...


class _Counters:
    """Thread-safe counters shared by the runners."""

    def __init__(self, workers: int) -> None:
        self._lock = threading.Lock()
        self._workers = workers
        self._queued = 0
        self._active = 0
        self._finished = 0
        self._errors = 0

    def enqueued(self) -> None:
        with self._lock:
            self._queued += 1

    def rejected(self) -> None:
        """Undo enqueued() when the job could not be scheduled."""
        with self._lock:
            self._queued -= 1

    def started(self) -> None:
        with self._lock:
            self._queued -= 1
            self._active += 1

    def finished(self, errored: bool) -> None:
        with self._lock:
            self._active -= 1
            self._finished += 1
            if errored:
                self._errors += 1

    def snapshot(self) -> RunnerStats:
        with self._lock:
            return RunnerStats(
                workers=self._workers,
                queued=self._queued,
                active=self._active,
                finished=self._finished,
                errors=self._errors,
            )


def _execute(service: FileService, file_id: str, content: bytes) -> bool:
    """Run one job. run_job records failures itself; this is the last safety net.

    Returns True when an exception escaped run_job (and was logged).
    """
    try:
        service.run_job(file_id, content)
    except Exception:  # noqa: BLE001 - a job error must never kill a worker thread
        logger.exception("job_runner_error", extra={"file_id": file_id})
        return True
    return False


def _tracked(
    counters: _Counters, service: FileService, file_id: str, content: bytes
) -> None:
    """Run one job and keep the counters right, even if it errors."""
    counters.started()
    errored = True  # stays True only if _execute itself blows up
    try:
        errored = _execute(service, file_id, content)
    finally:
        counters.finished(errored)


class InlineJobRunner:
    """Runs the job immediately in the calling thread (tests, simple scripts)."""

    def __init__(self, service: FileService) -> None:
        self._service = service
        self._counters = _Counters(workers=1)

    def submit(self, file_id: str, content: bytes) -> None:
        self._counters.enqueued()
        _tracked(self._counters, self._service, file_id, content)

    def shutdown(self, wait: bool = True) -> None:
        return None

    def stats(self) -> RunnerStats:
        return self._counters.snapshot()


class ThreadPoolJobRunner:
    """Runs jobs on a small pool of background threads."""

    def __init__(self, service: FileService, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._service = service
        self._counters = _Counters(workers=max_workers)
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="job-worker"
        )

    def submit(self, file_id: str, content: bytes) -> None:
        # Count first: a fast worker could otherwise start before we count it.
        self._counters.enqueued()
        try:
            self._pool.submit(
                _tracked, self._counters, self._service, file_id, content
            )
        except Exception:
            # e.g. the pool is already shut down. Keep the counter honest.
            self._counters.rejected()
            raise

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def stats(self) -> RunnerStats:
        return self._counters.snapshot()